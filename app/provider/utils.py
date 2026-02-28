from datetime import datetime, timedelta
from typing import List, Optional
from app.schemas.schemas import ExamInstance, CourseInstance, ScheduleSchema


def weekday_to_date(week: int, day: int, week_1_monday: datetime):
    days_offset = (week - 1) * 7 + (day - 1)
    target_date = week_1_monday + timedelta(days=days_offset)
    return target_date.strftime('%Y-%m-%d')


def exams_to_course(exams: List[ExamInstance], week_1_monday: Optional[datetime] = None) -> List[CourseInstance]:
    course_instances = []
    for exam in exams:
        if week_1_monday and exam.week and exam.day:
            date = weekday_to_date(exam.week, exam.day, week_1_monday)
        else:
            date = exam.date
        if date is None:
            continue
        course_instances.append(CourseInstance(
            course=f"【{exam.type}】{exam.course}",
            teacher="未知",
            week=exam.week,
            day=exam.day,
            periods=exam.periods,
            date=date,
            start_time=exam.start_time,
            end_time=exam.end_time,
            location=f"{exam.location} {exam.seat}",
            description=None,
            conflicts=None,
            type="考试"
        ))
    return course_instances


def resolve_schedule_conflicts(schedule: ScheduleSchema) -> ScheduleSchema:
    """
    检查并合并课程冲突。
    如果 week, day, periods 发生冲突，则合并为一个 CourseInstance，并将原始课程存入 conflicts。
    """
    # 1. 建立槽位映射 (week, day, period) -> merged_instances 的索引
    slot_map = {}
    merged_instances: List[CourseInstance] = []

    # 按时间排序（周次、星期、开始节次）
    original_instances = sorted(
        schedule.instances,
        key=lambda x: (x.week or 0, x.day or 0,
                       x.periods[0] if x.periods else 0)
    )

    def get_course_detail_text(num: int, inst: CourseInstance) -> str:
        """格式化单条冲突详情文本"""
        return (
            f"# {num}\\n"
            f"课程：{inst.course}\\n"
            f"教师：{inst.teacher}\\n"
            f"时间：{inst.start_time} - {inst.end_time}\\n"
            f"日期：{inst.date}\\n"
            f"地点：{inst.location}\\n"
        )

    for inst in original_instances:
        # 跳过无效数据
        if inst.week is None or inst.day is None:
            merged_instances.append(inst)
            continue

        conflict_idx = None
        # 检查当前课程的任一节次是否已被占用
        for p in inst.periods:
            key = (inst.week, inst.day, p)
            if key in slot_map:
                conflict_idx = slot_map[key]
                break

        if conflict_idx is not None:
            # --- 发现冲突，合并到现有实例 ---
            existing = merged_instances[conflict_idx]

            # 1. 如果是第一次发现冲突（conflicts 为 None）
            if existing.conflicts is None:
                # 备份第一个课程，清空其 conflicts 属性防止循环引用
                first_backup = existing.model_copy()
                first_backup.conflicts = None

                existing.conflicts = [first_backup]
                existing.type = "冲突"
                # 初始化描述
                existing.description = f"【冲突详情】\\n{get_course_detail_text(1, first_backup)}"

            # 2. 备份当前冲突的课程并加入列表
            inst_backup = inst.model_copy()
            inst_backup.conflicts = None  # 切断嵌套引用
            existing.conflicts.append(inst_backup)

            # 3. 更新描述文本（追加第 N 个详情）
            count = len(existing.conflicts)
            existing.description += f"\\n{get_course_detail_text(count, inst)}"

            # 4. 更新基础显示字段（拼接名称和老师）
            if inst.course not in existing.course:
                existing.course = f"{existing.course} / {inst.course}"
            if inst.teacher and inst.teacher not in existing.teacher:
                existing.teacher = f"{existing.teacher} / {inst.teacher}"

            # 5. 合并并重新映射所有节次
            existing.periods = sorted(
                list(set(existing.periods + inst.periods)))
            for p in existing.periods:
                slot_map[(inst.week, inst.day, p)] = conflict_idx

        else:
            # --- 无冲突，作为新项加入 ---
            current_idx = len(merged_instances)
            new_item = inst.model_copy()
            # 明确初始化为 None，确保没有冲突时 JSON 不包含多余数据
            new_item.conflicts = None
            merged_instances.append(new_item)
            for p in inst.periods:
                slot_map[(inst.week, inst.day, p)] = current_idx

    # 将处理后的列表回填
    schedule.instances = merged_instances
    return schedule


def sort_schedule_by_time(schedule: ScheduleSchema) -> ScheduleSchema:
    """
    对课程/考试实例进行排序：
    1. 日期从近到远 (2025-09-01 -> 2026-01-01)
    2. 同一天内，按起始时间从早到晚 (08:00 -> 19:00)
    """
    if not schedule.instances:
        return schedule

    # 使用 sorted 进行多级排序
    # key 返回一个元组：(日期, 开始时间)
    # 字符串格式的 '2025-02-28' 和 '08:00' 直接比较即可实现时间先后排序
    sorted_instances = sorted(
        schedule.instances,
        key=lambda x: (
            x.date if x.date else "9999-12-31",  # 缺失日期排到最后
            x.start_time if x.start_time else "23:59"  # 缺失时间排到最后
        )
    )

    schedule.instances = sorted_instances
    return schedule
