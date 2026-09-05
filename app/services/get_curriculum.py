import asyncio
import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks

from app.core.config import get_next_curriculum_week_1_monday
from app.core.database import database
from app.exceptions.JwzxError import JwzxError
from app.provider.adjustments import apply_holiday_adjustments
from app.provider.parse_jwzx_kebiao import (
    extract_schedule_metadata,
    parse_jwzx_kebiao,
)
from app.provider.parse_jwzx_ksap import parse_jwzx_ksap, parse_jwzx_ksapBk
from app.provider.request_jwzx import (
    request_jwzx_kebiao,
    request_jwzx_ksap,
    request_jwzx_ksapBk,
    request_jwzx_next_kebiao,
)
from app.provider.utils import (
    exams_to_course,
    resolve_schedule_conflicts,
    sort_schedule_by_time,
)
from app.schemas.schemas import ScheduleSchema


CACHE_MAX_AGE_SECONDS = int(os.getenv("CACHE_MAX_AGE_SECONDS", "5"))
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _is_stale(fetched_at: Optional[datetime]) -> bool:
    if fetched_at is None:
        return True
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched_at).total_seconds() > CACHE_MAX_AGE_SECONDS


def _with_updated_at(
    data: Optional[ScheduleSchema], fetched_at: Optional[datetime]
) -> Optional[ScheduleSchema]:
    if data is not None and fetched_at is not None:
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        data.updated_at = fetched_at.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
    return data


def _as_local_naive(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)
    if value.tzinfo is not None:
        value = value.astimezone(SHANGHAI_TZ).replace(tzinfo=None)
    return value


async def _request_and_cache_current(student_id: str) -> Tuple[str, str, str, datetime]:
    """并发请求本学期课表、考试和补考页，然后原子写入 PostgreSQL。"""
    kebiao_html, ksap_html, ksapbk_html = await asyncio.gather(
        request_jwzx_kebiao(student_id),
        request_jwzx_ksap(student_id),
        request_jwzx_ksapBk(student_id),
    )
    student_name, academic_year, semester = extract_schedule_metadata(kebiao_html)
    if student_name is None:
        raise JwzxError("无法从本学期课表中识别学生姓名，拒绝入库。")
    if academic_year is None or semester is None:
        raise JwzxError("无法从本学期课表中识别学年学期，拒绝入库。")
    fetched_at = datetime.now(timezone.utc)
    await database.save_current_cache(
        student_id=student_id,
        academic_year=academic_year,
        semester=semester,
        student_name=student_name,
        kebiao_html=kebiao_html,
        ksap_html=ksap_html,
        ksapbk_html=ksapbk_html,
        kebiao_fetched_at=fetched_at,
        ksap_fetched_at=fetched_at,
        ksapbk_fetched_at=fetched_at,
    )
    return kebiao_html, ksap_html, ksapbk_html, fetched_at


async def _request_and_cache_next(student_id: str) -> Tuple[str, datetime]:
    """请求下学期公示课表并写入 PostgreSQL。"""
    html = await request_jwzx_next_kebiao(student_id)
    student_name, academic_year, semester = extract_schedule_metadata(html)
    if student_name is None:
        raise JwzxError("无法从下学期课表中识别学生姓名，拒绝入库。")
    if academic_year is None or semester is None:
        raise JwzxError("无法从下学期课表中识别学年学期，拒绝入库。")
    fetched_at = datetime.now(timezone.utc)
    await database.save_next_cache(
        student_id=student_id,
        academic_year=academic_year,
        semester=semester,
        student_name=student_name,
        html=html,
        fetched_at=fetched_at,
    )
    return html, fetched_at


async def update_current_cache(student_id: str) -> None:
    """后台静默更新本学期数据。"""
    try:
        await _request_and_cache_current(student_id)
    except Exception:
        pass


async def update_next_cache(student_id: str) -> None:
    """后台静默更新下学期数据。"""
    try:
        await _request_and_cache_next(student_id)
    except Exception:
        pass


def parse_all_data(
    request_at: datetime,
    kb_html: str,
    ks_html: str,
    bk_html: str,
) -> Optional[ScheduleSchema]:
    """解析本学期课表、考试、补考和调休数据。"""
    try:
        curriculum_data = parse_jwzx_kebiao(kb_html, request_at=request_at)
    except JwzxError:
        return None

    exam_data, exam_academic_year, exam_semester = parse_jwzx_ksap(ks_html)
    exam_bk_data = parse_jwzx_ksapBk(bk_html)

    all_exam_instances = []
    if (
        exam_academic_year == curriculum_data.academic_year
        and exam_semester == curriculum_data.semester
    ):
        all_exam_instances.extend(exam_data)
    if exam_bk_data:
        all_exam_instances.extend(exam_bk_data)

    for exam in all_exam_instances:
        if not exam.teacher:
            for course in curriculum_data.instances:
                if exam.course in course.course or course.course in exam.course:
                    exam.teacher = course.teacher
                    break
            if not exam.teacher:
                exam.teacher = "未知教师"

    exam_courses = exams_to_course(all_exam_instances, curriculum_data.week_1_monday)
    for exam_course in exam_courses:
        if exam_course.week is None:
            exam_course.week = 0

    curriculum_data.instances.extend(exam_courses)
    curriculum_data = apply_holiday_adjustments(curriculum_data)
    curriculum_data = resolve_schedule_conflicts(curriculum_data)
    return sort_schedule_by_time(curriculum_data)


def parse_next_data(html: str) -> ScheduleSchema:
    """解析下学期公示课表；不混入本学期的考试和补考。"""
    curriculum_data = parse_jwzx_kebiao(
        html,
        week_1_monday=get_next_curriculum_week_1_monday(),
    )
    curriculum_data = resolve_schedule_conflicts(curriculum_data)
    return sort_schedule_by_time(curriculum_data)


async def get_curriculum_data(
    student_id: str, background_tasks: BackgroundTasks
) -> Optional[ScheduleSchema]:
    cache = await database.get_latest_current_cache(student_id)
    current_fields = ("kebiao_html", "ksap_html", "ksapbk_html")

    if cache and all(cache.get(field) for field in current_fields):
        timestamps = (
            cache.get("kebiao_fetched_at"),
            cache.get("ksap_fetched_at"),
            cache.get("ksapbk_fetched_at"),
        )
        if any(_is_stale(value) for value in timestamps):
            background_tasks.add_task(update_current_cache, student_id)

        data = parse_all_data(
            _as_local_naive(cache.get("kebiao_fetched_at")),
            cache["kebiao_html"],
            cache["ksap_html"],
            cache["ksapbk_html"],
        )

        return _with_updated_at(data, cache.get("kebiao_fetched_at"))

    kb_html, ks_html, bk_html, fetched_at = await _request_and_cache_current(student_id)
    data = parse_all_data(
        _as_local_naive(fetched_at),
        kb_html,
        ks_html,
        bk_html,
    )

    return _with_updated_at(data, fetched_at)


async def get_next_curriculum_data(
    student_id: str, background_tasks: BackgroundTasks
) -> ScheduleSchema:
    cache = await database.get_latest_next_cache(student_id)
    if cache and cache.get("next_kebiao_html"):
        if _is_stale(cache.get("next_kebiao_fetched_at")):
            background_tasks.add_task(update_next_cache, student_id)
        data = parse_next_data(cache["next_kebiao_html"])
        _with_updated_at(data, cache.get("next_kebiao_fetched_at"))
        return data

    html, fetched_at = await _request_and_cache_next(student_id)
    data = parse_next_data(html)
    _with_updated_at(data, fetched_at)
    return data
