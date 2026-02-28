from datetime import datetime
from typing import Dict, Any
from app.schemas.schemas import ScheduleSchema


def get_schedule_overview(data: ScheduleSchema) -> Dict[str, Any]:
    now = datetime.now()
    # 转换为 HH:MM 格式进行字符串比较
    current_time_str = now.strftime('%H:%M')

    # 0 是周一, 6 是周日。教务在线的数据 day 是 1-7。
    # 我们将其统一为 1-7 (周一到周日)
    day_today = now.isoweekday()
    day_tomorrow = (day_today % 7) + 1

    # 计算当前是第几周 (基于解析出的 week_1_monday)
    diff = now - data.week_1_monday
    now_week = (diff.days // 7) + 1 if diff.days >= 0 else 0

    current_courses = []
    today_courses = []
    tomorrow_courses = []

    for inst in data.instances:
        # 只处理本周的课
        if inst.week == now_week:
            simplified = {
                "name": inst.course,
                "begin": inst.start_time,
                "end": inst.end_time,
                "location": inst.location,
                "teacher": inst.teacher
            }

            # 处理今天
            if inst.day == day_today:
                today_courses.append(simplified)
                # 判断是否正在上
                if inst.start_time <= current_time_str <= inst.end_time:
                    current_courses.append(simplified)

            # 处理明天
            if inst.day == day_tomorrow:
                tomorrow_courses.append(simplified)

    # 排序
    def sort_key(x): return x['begin']
    today_courses.sort(key=sort_key)
    tomorrow_courses.sort(key=sort_key)
    current_courses.sort(key=sort_key)

    return {
        "currentCourses": current_courses,
        "todayCourses": today_courses,
        "tomorrowCourses": tomorrow_courses,
        "nowWeek": now_week,
        # "studentName": data.student_name
    }
