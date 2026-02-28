from typing import List
from app.schemas.schemas import ScheduleSchema


def generate_ics(data: ScheduleSchema, alarms: List[int]) -> str:
    """
    alarms: 包含提醒分钟数的列表，例如 [30, 10]
    """
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//CQUPT//Course//CN",
        "X-WR-CALNAME:重邮课表",
        "X-WR-TIMEZONE:Asia/Shanghai"
    ]

    for idx, ev in enumerate(data.instances):
        s_t, e_t = ev.start_time, ev.end_time
        class_name = ev.course if ev.type in [
            "常规", "考试"] else f"{ev.course} ({ev.type})"
        date = ev.date.replace('-', '')

        ics_line = [
            "BEGIN:VEVENT",
            f"UID:event_{idx}_{date}@school",
            f"DTSTART;TZID=Asia/Shanghai:{date}T{s_t.replace(':', '')}00",
            f"DTEND;TZID=Asia/Shanghai:{date}T{e_t.replace(':', '')}00",
            f"SUMMARY:{class_name}",
        ]
        if ev.type == "考试":
            ics_line.append(f"LOCATION:{ev.location}")
            ics_line.append(
                f"DESCRIPTION:地点：{ev.location.split(' ')[0]}\\n座位号: {ev.location.split(' ')[1]}\\n教师: {ev.teacher}\\n类型: {ev.type}\\n节次: {ev.periods}")
        elif ev.type == "冲突":
            ics_line.append(f"LOCATION:{ev.location}")
            ics_line.append(
                f"DESCRIPTION:{ev.description}")
        else:
            ics_line.append(f"LOCATION:{ev.location} {ev.teacher}")
            ics_line.append(
                f"DESCRIPTION:地点：{ev.location}\\n教师: {ev.teacher}\\n类型: {ev.type}\\n节次: {ev.periods}")

        ics_lines.extend(ics_line)

        # 动态添加提醒
        for minutes in alarms:
            ics_lines.extend([
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                f"DESCRIPTION:{class_name} @ {ev.location}",
                f"TRIGGER:-PT{minutes}M",
                "END:VALARM"
            ])

        ics_lines.append("END:VEVENT")

    ics_lines.append("END:VCALENDAR")
    return "\n".join(ics_lines)
