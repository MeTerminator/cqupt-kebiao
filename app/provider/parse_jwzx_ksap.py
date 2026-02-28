import re
from datetime import datetime
from bs4 import BeautifulSoup
from app.schemas.schemas import ExamInstance
from app.exceptions.JwzxError import JwzxError

# 时间段到节次的映射表
TIME_TO_PERIODS = {
    "07:50-09:50": [1, 2],
    "10:10-12:10": [3, 4],
    "13:50-15:50": [5, 6],
    "16:10-18:10": [7, 8],
    "19:30-21:30": [9, 10],
}


def _parse_time_info(time_str: str):
    """解析时间信息，优先提取节次，若无节次则根据时间映射"""
    periods_match = re.search(r"第(\d+)-(\d+)节", time_str)
    times = re.findall(r"(\d{1,2}:\d{2})", time_str)

    start_time = times[0] if len(times) > 0 else ""
    end_time = times[1] if len(times) > 1 else ""

    periods = []
    if periods_match:
        start_p, end_p = map(int, periods_match.groups())
        periods = list(range(start_p, end_p + 1))
    elif start_time and end_time:
        time_range = f"{start_time.zfill(5)}-{end_time.zfill(5)}"
        periods = TIME_TO_PERIODS.get(time_range, [])

    return periods, start_time, end_time


def parse_jwzx_ksap(html: str) -> tuple[list[ExamInstance], str, str]:
    """解析普通考试安排"""
    soup = BeautifulSoup(html, "html.parser")
    exams = []

    head_text = soup.find('div', id='head')
    if not head_text:
        # 教务在线晚上无法正常返回信息
        raise JwzxError("教务在线数据获取失败，请在白天重试。")

    head_text = head_text.get_text(separator=' ', strip=True)

    term_match = re.search(r'(\d{4}-\d{4})学年(\d)学期', head_text)
    academic_year = term_match.group(1) if term_match else "未知学年"
    semester = term_match.group(2) if term_match else "未知学期"

    table = soup.find("table")
    if not table:
        return [], academic_year, semester
    tbody = table.find("tbody")
    if not tbody:
        return [], academic_year, semester

    for row in tbody.find_all("tr"):
        cols = [ele.text.strip() for ele in row.find_all("td")]
        if len(cols) < 11:
            continue

        periods, start, end = _parse_time_info(cols[8])

        week_val = None
        week_match = re.search(r"(\d+)", cols[6])
        if week_match:
            week_val = int(week_match.group(1))

        exams.append(ExamInstance(
            course=cols[5],
            teacher=None,
            week=week_val,
            day=int(cols[7]) if cols[7].isdigit() else None,
            periods=periods,
            date=None,  # 普通考试页面通常没有具体日期列
            start_time=start,
            end_time=end,
            location=cols[9],
            seat=cols[10],
            type=cols[3]
        ))
    return exams, academic_year, semester


def parse_jwzx_ksapBk(html: str) -> list[ExamInstance]:
    """解析补考考试安排"""
    if "没有找到该学号补考安排信息" in html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    exams = []
    table = soup.find("table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []

    for row in tbody.find_all("tr"):
        cols = [ele.text.strip() for ele in row.find_all("td")]
        if len(cols) < 9:
            continue

        course_name = cols[4].split('-')[-1] if '-' in cols[4] else cols[4]
        periods, start, end = _parse_time_info(cols[6])

        # 处理日期并统一格式为 YYYY-MM-DD
        formatted_date = None
        exam_day = None
        raw_date = cols[5]

        if raw_date.isdigit() and len(raw_date) == 8:
            try:
                dt = datetime.strptime(raw_date, "%Y%m%d")
                formatted_date = dt.strftime("%Y-%m-%d")
                exam_day = dt.isoweekday()
            except ValueError:
                pass

        exams.append(ExamInstance(
            course=course_name,
            teacher=None,
            week=None,
            day=exam_day,
            periods=periods,
            date=formatted_date,
            start_time=start,
            end_time=end,
            location=cols[7],
            seat=cols[8],
            type="补考"
        ))
    return exams
