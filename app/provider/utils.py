from datetime import datetime, timedelta
from typing import List, Optional
from app.schemas.schemas import ExamInstance, CourseInstance


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
            type="考试"
        ))
    return course_instances
