from datetime import datetime, timedelta
from typing import Dict, Any
from app.schemas.schemas import ScheduleSchema


def get_schedule_overview(data: ScheduleSchema) -> Dict[str, Any]:
    now = datetime.now()
    tomorrow = now + timedelta(days=1)

    current_time_str = now.strftime('%H:%M')

    # 计算“今天”和“明天”分别对应的周数和周几
    def get_week_and_day(target_date: datetime):
        diff = target_date - data.week_1_monday
        days_diff = diff.days
        if days_diff < 0:
            week = 0 if days_diff >= -7 else -1
        else:
            week = (days_diff // 7) + 1

        # isoweekday: 1(周一) - 7(周日)
        return week, target_date.isoweekday()

    now_week, day_today = get_week_and_day(now)
    tomorrow_week, day_tomorrow = get_week_and_day(tomorrow)

    current_courses = []
    today_courses = []
    tomorrow_courses = []

    for inst in data.instances:
        simplified = {
            "name": inst.course,
            "begin": inst.start_time,
            "end": inst.end_time,
            "location": inst.location,
            "teacher": inst.teacher
        }

        # 1. 处理今天（当前周 & 今天）
        if inst.week == now_week and inst.day == day_today:
            today_courses.append(simplified)
            # 判断当前是否有课
            if inst.start_time <= current_time_str <= inst.end_time:
                current_courses.append(simplified)

        # 2. 处理明天（注意：这里的 tomorrow_week 可能比 now_week 大 1）
        if inst.week == tomorrow_week and inst.day == day_tomorrow:
            tomorrow_courses.append(simplified)

    # 排序函数
    def sort_key(x): return x['begin']
    today_courses.sort(key=sort_key)
    tomorrow_courses.sort(key=sort_key)
    current_courses.sort(key=sort_key)

    return {
        "currentCourses": current_courses,
        "todayCourses": today_courses,
        "tomorrowCourses": tomorrow_courses,
        "nowWeek": now_week,
    }
