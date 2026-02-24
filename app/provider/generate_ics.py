from datetime import timedelta
from app.schemas.schedule_instances import ScheduleSchema


def generate_ics(data: ScheduleSchema) -> str:
    """
    传入 ScheduleSchema 模型，返回 ICS 字符串内容
    """
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CQUPT//Course//CN",
        "X-WR-CALNAME:重邮课表",
        "X-WR-TIMEZONE:Asia/Shanghai"
    ]

    for idx, ev in enumerate(data.instances):

        # 获取起止时间
        s_t, e_t = ev.start_time, ev.end_time

        class_name = ev.course if ev.type == "常规" else f"{ev.course} ({ev.type})"

        date = ev.date.replace('-', '')

        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:event_{idx}_{date}@school",
            f"DTSTART;TZID=Asia/Shanghai:{date}T{s_t.replace(':', '')}00",
            f"DTEND;TZID=Asia/Shanghai:{date}T{e_t.replace(':', '')}00",
            f"SUMMARY:{class_name}",
            f"LOCATION:{ev.location} {ev.teacher}",
            f"DESCRIPTION:地点：{ev.location}\\n教师: {ev.teacher}\\n类型: {ev.type}\\n节次: {ev.periods}",
            "END:VEVENT"
        ])

    ics_lines.append("END:VCALENDAR")
    return "\n".join(ics_lines)
