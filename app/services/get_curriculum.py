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
    """解析课表、考试、补考数据"""
    # 解析课表数据
    try:
        curriculum_data = parse_jwzx_kebiao(kb_html, request_at=request_at)
    except JwzxError:
        return None

    exam_data, exam_academic_year, exam_semester = parse_jwzx_ksap(ks_html)
    exam_bk_data = parse_jwzx_ksapBk(bk_html)

    if exam_bk_data:
        exam_data.extend(exam_bk_data)

    # 给考试科目找一个老师
    for exam in exam_data:
        if exam.teacher is None:
            for course in curriculum_data.instances:
                if exam.course in course.course:
                    exam.teacher = course.teacher
                    break

    week_1_monday = curriculum_data.week_1_monday
    exam_data_parsed = exams_to_course(exam_data, week_1_monday)

    # 如果学期和考试学年不一致，则不显示考试数据
    if exam_academic_year == curriculum_data.academic_year and exam_semester == curriculum_data.semester:
        curriculum_data.instances.extend(exam_data_parsed)

    # 合并冲突课程
    curriculum_data = resolve_schedule_conflicts(curriculum_data)

    # 排序
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
