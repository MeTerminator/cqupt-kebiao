import asyncio
from datetime import datetime
from typing import Optional, Tuple
from fastapi import BackgroundTasks

from app.core.redis import redis_client
from app.provider.request_jwzx import request_jwzx_kebiao, request_jwzx_ksap, request_jwzx_ksapBk
from app.provider.parse_jwzx_kebiao import parse_jwzx_kebiao
from app.provider.parse_jwzx_ksap import parse_jwzx_ksap, parse_jwzx_ksapBk
from app.provider.utils import exams_to_course, resolve_schedule_conflicts, sort_schedule_by_time
from app.schemas.schemas import ScheduleSchema
from app.exceptions.JwzxError import JwzxError
from app.schemas.schemas import ScheduleSchema

# 定义常量方便维护
CACHE_KEYS = ["kebiao_html", "ksap_html", "ksapbk_html"]
TS_KEYS = [f"{k}_ts" for k in CACHE_KEYS]


async def _request_and_cache(student_id: str) -> Tuple[str, str, str]:
    """并发请求三个接口并统一写入缓存"""
    # 并发请求，节省等待时间
    kebiao_html, ksap_html, ksapbk_html = await asyncio.gather(
        request_jwzx_kebiao(student_id),
        request_jwzx_ksap(student_id),
        request_jwzx_ksapBk(student_id)
    )

    now_ts = datetime.now().timestamp()

    # 统一使用一个 pipeline 写入所有数据
    async with redis_client.pipeline(transaction=True) as pipe:
        data_map = {
            f"kebiao_html:{student_id}": kebiao_html,
            f"ksap_html:{student_id}": ksap_html,
            f"ksapbk_html:{student_id}": ksapbk_html,
            f"kebiao_html_ts:{student_id}": now_ts,
            f"ksap_html_ts:{student_id}": now_ts,
            f"ksapbk_html_ts:{student_id}": now_ts,
        }
        for key, val in data_map.items():
            pipe.set(key, val, ex=3600)
        await pipe.execute()

    return kebiao_html, ksap_html, ksapbk_html


async def update_cache(student_id: str):
    """静默更新"""
    try:
        await _request_and_cache(student_id)
    except Exception:
        pass


def parse_all_data(request_at: datetime, kb_html: str, ks_html: str, bk_html: str) -> Optional[ScheduleSchema]:
    """解析课表、考试、补考数据并进行合并、冲突处理与排序"""

    # 1. 解析课表基础数据
    try:
        curriculum_data = parse_jwzx_kebiao(kb_html, request_at=request_at)
    except JwzxError:
        return None

    # 2. 解析普通考试和补考数据
    # 假设 parse_jwzx_ksap 返回 (exams: list[ExamInstance], year: str, term: str)
    exam_data, exam_academic_year, exam_semester = parse_jwzx_ksap(ks_html)
    exam_bk_data = parse_jwzx_ksapBk(bk_html)  # 补考数据，type通常已在解析时设为"补考"

    # 3. 统一处理考试列表
    all_exam_instances = []

    # 策略：普通考试受学年学期限制，补考不受限制（补考通常是考上学期的课）
    # 先处理普通考试
    if exam_academic_year == curriculum_data.academic_year and exam_semester == curriculum_data.semester:
        all_exam_instances.extend(exam_data)

    # 始终添加补考数据
    if exam_bk_data:
        all_exam_instances.extend(exam_bk_data)

    # 4. 补全老师信息（尝试从课表中匹配同名课程的老师）
    for exam in all_exam_instances:
        if not exam.teacher:
            for course in curriculum_data.instances:
                # 模糊匹配：考试名在课程名中或反之
                if exam.course in course.course or course.course in exam.course:
                    exam.teacher = course.teacher
                    break
            # 如果还是没找到，设为未知
            if not exam.teacher:
                exam.teacher = "未知教师"

    # 5. 将 ExamInstance 转换为 CourseInstance 统一模型
    # 假设 exams_to_course 会处理 date, start_time, end_time 等转换
    week_1_monday = curriculum_data.week_1_monday
    exam_courses = exams_to_course(all_exam_instances, week_1_monday)

    # 6. 处理补考/异常考试的周次
    # 补考可能没有 week，为了排序和模型校验，统一设为 0 或计算出的实际周次
    for ec in exam_courses:
        if ec.week is None:
            ec.week = 0

    # 7. 合并到主课表实例中
    curriculum_data.instances.extend(exam_courses)

    # 8. 处理冲突课程（按照你要求的 #1, #2 格式合并 description）
    curriculum_data = resolve_schedule_conflicts(curriculum_data)

    # 9. 全局排序（按照日期和起始时间从近到远）
    curriculum_data = sort_schedule_by_time(curriculum_data)

    return curriculum_data


async def get_curriculum_data(student_id: str, background_tasks: BackgroundTasks) -> Optional[ScheduleSchema]:
    # 1. 构造 Redis Key 列表
    all_keys = [f"{k}:{student_id}" for k in CACHE_KEYS + TS_KEYS]

    # 2. 使用 mget 一次性获取所有缓存数据 (顺序: 课表, 考试, 补考, 课表TS, 考试TS, 补考TS)
    values = await redis_client.mget(*all_keys)

    kb_html, ks_html, bk_html = values[0:3]
    ts_values = values[3:6]

    now_ts = datetime.now().timestamp()

    # 3. 检查缓存完整性
    if all(values[:3]):  # 如果三个 HTML 都有缓存
        # 4. 检查是否有任意一个超过 5s
        try:
            # 只要有一个时间戳不存在，或者当前时间减去任意一个时间戳 > 5
            needs_update = False
            if not all(ts_values):
                needs_update = True
            else:
                # 任意一个超过 5s 即为 True
                needs_update = any((now_ts - float(ts)) >
                                   5 for ts in ts_values)

            if needs_update:
                background_tasks.add_task(update_cache, student_id)
        except (ValueError, TypeError):
            background_tasks.add_task(update_cache, student_id)

        # 解析并返回（这里 request_at 取课表的时间戳作为代表）
        ref_dt = datetime.fromtimestamp(
            float(ts_values[0])) if ts_values[0] else datetime.now()

        return parse_all_data(ref_dt, kb_html, ks_html, bk_html)

    # 5. 无完整缓存：阻塞请求
    try:
        kb_html, ks_html, bk_html = await _request_and_cache(student_id)
        # 阻塞请求返回最新解析结果
        return parse_all_data(datetime.now(), kb_html, ks_html, bk_html)
    except Exception:
        raise
