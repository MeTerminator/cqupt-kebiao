import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from pydantic import ValidationError

from app.schemas.schedule_instances import ScheduleSchema, CourseInstance
from app.exceptions.JwzxError import JwzxError


# 课表 HTML 来源
# http://jwzx.cqupt.edu.cn/kebiao/kb_stu.php?xh=<学号>


def get_period_time(period):
    start_map = {
        1: "08:00", 2: "08:55", 3: "10:15", 4: "11:10",
        5: "14:00", 6: "14:55", 7: "16:15", 8: "17:10",
        9: "19:00", 10: "19:55", 11: "20:50", 12: "21:45",
    }
    try:
        s_p, e_p = int(period[0]), int(period[-1])
        start_t = start_map[s_p]
        end_start_t = datetime.strptime(start_map[e_p], "%H:%M")
        end_t = (end_start_t + timedelta(minutes=45)).strftime("%H:%M")
        return start_t, end_t
    except:
        return "08:00", "08:45"


def parse_week_string(week_str):
    weeks = set()
    if not week_str:
        return []
    is_even = '双周' in week_str
    is_odd = '单周' in week_str
    parts = re.findall(r'(\d+)-(\d+)|\b(\d+)\b', week_str.replace('周', ''))
    for start, end, single in parts:
        if single:
            weeks.add(int(single))
        elif start and end:
            for w in range(int(start), int(end) + 1):
                if is_even and w % 2 != 0:
                    continue
                if is_odd and w % 2 == 0:
                    continue
                weeks.add(w)
    return sorted(list(weeks))


def parse_time_detail(text):
    """解析如 '18周星期3第1-2节' 或 '星期2第5-6节'"""
    week_m = re.search(r'(\d+(?:-\d+)?)周', text)
    day_m = re.search(r'星期(\d+)', text)
    per_m = re.search(r'第(\d+(?:-\d+)?)节', text)

    weeks = parse_week_string(week_m.group(1)) if week_m else []
    day = int(day_m.group(1)) if day_m else None
    periods = per_m.group(1) if per_m else None
    return weeks, day, periods


def get_period_numbers(period_str):
    """将 '5-7' 或 '5、6' 转化为 [5, 6, 7]"""
    nums = re.findall(r'\d+', str(period_str))
    if not nums:
        return []
    if '-' in str(period_str) or '节' in str(period_str):
        start, end = int(nums[0]), int(nums[-1])
        return list(range(start, end + 1))
    return [int(n) for n in nums]


def parse_jwzx_kebiao(html_content) -> ScheduleSchema:
    soup = BeautifulSoup(html_content, 'html.parser')

    # --- 1. 动态推算第一周周一 ---
    head_text = soup.find('div', id='head')
    if not head_text:
        # 教务在线晚上无法正常返回信息
        raise JwzxError("教务在线数据获取失败，请在白天重试。")

    head_text = head_text.get_text(separator=' ', strip=True)

    term_match = re.search(r'(\d{4}-\d{4})学年(\d)学期', head_text)
    academic_year = term_match.group(1) if term_match else "未知学年"
    semester = term_match.group(2) if term_match else "未知学期"

    info = re.search(r'今天是第\s*(\d+)\s*周\s*星期\s*(\d+)', head_text)
    if info:
        curr_w, curr_d = int(info.group(1)), int(info.group(2))
        today = datetime.now()
        week_1_monday = today - \
            timedelta(days=today.weekday()) - timedelta(weeks=(curr_w - 1))

        # 提取学号姓名
        stu_match = re.search(r'(\d{10})([\u4e00-\u9fa5]+)', head_text)
        student_id = stu_match.group(1) if stu_match else "未知学号"
        student_name = stu_match.group(2) if stu_match else "未知姓名"
    else:
        week_1_monday = datetime(2025, 9, 1)

    week_1_monday = week_1_monday.replace(
        hour=0, minute=0, second=0, microsecond=0)

    schedule_instances = []

    # --- 2. 解析常规课表表格 ---
    table = soup.select_one('#stuPanel table')
    if table:
        rows = table.find_all('tr')[1:]
        for row in rows:
            tds = row.find_all('td')
            if not tds or "节" not in tds[0].get_text():
                continue
            period_name = tds[0].get_text(strip=True)
            for day_idx, td in enumerate(tds[1:], start=1):
                for div in td.find_all('div', class_='kbTd'):
                    lines = [l.strip() for l in div.get_text(
                        separator='\n').split('\n') if l.strip()]
                    if len(lines) < 3:
                        continue

                    current_periods = period_name
                    if "3节连上" in div.get_text():
                        start_p = int(re.findall(r'\d+', period_name)[0])
                        current_periods = f"{start_p}-{start_p+2}"

                    if "3节连上" in lines:
                        lines.remove("3节连上")

                    course_name = lines[1].split('-')[-1]
                    location = lines[2].replace('地点：', '')
                    week_str = lines[3]
                    teacher = lines[4].split(' ')[0] if len(lines) > 4 else ""

                    current_periods = get_period_numbers(current_periods)

                    weeks = parse_week_string(week_str)
                    for w in weeks:
                        schedule_instances.append({
                            'course': course_name,
                            'teacher': teacher,
                            'week': w,
                            'day': day_idx,
                            'periods': current_periods,
                            'location': location,
                            'type': '常规',
                        })

    # --- 3. 解析调停课 ---
    ttk_table = soup.select_one('#kbStuTabs-ttk table')
    if ttk_table:
        for tr in ttk_table.find_all('tr')[1:]:
            tds = [td.get_text(strip=True) for td in tr.find_all('td')]
            if len(tds) < 11:
                continue

            # 类型：停课/补课/代课
            op_type = tds[2]
            course_name = tds[4]
            orig_teacher = tds[5]

            # 无论什么类型，先解析出受影响的时间范围
            if op_type == '停课':
                affected_weeks = parse_week_string(tds[6])
                _, affected_day, affected_per_str = parse_time_detail(tds[7])
            else:
                # 补课或代课
                affected_weeks, affected_day, affected_per_str = parse_time_detail(
                    tds[8])

            if not affected_day or not affected_per_str:
                continue

            # 将节次转为数字列表，例如 [5, 6]
            affected_periods = get_period_numbers(affected_per_str)

            # --- 去重：删除原课表中所有在受影响时间内、且课程名匹配(或时间重合)的课 ---
            new_schedule = []
            for inst in schedule_instances:
                inst_periods = get_period_numbers(inst['periods'])

                # 周次相同 且 星期相同 且 节次有重叠
                is_same_time = (inst['week'] in affected_weeks and
                                inst['day'] == affected_day and
                                any(p in inst_periods for p in affected_periods))

                # 如果是停课，匹配课程名和时间则删除
                if op_type == '停课':
                    if is_same_time and (course_name in inst['course']):
                        continue
                # 如果是代课/补课，只要时间冲突，就必须删除旧课，腾出位置
                elif op_type in ('代课', '补课'):
                    if is_same_time:
                        continue

                new_schedule.append(inst)

            schedule_instances = new_schedule

            # --- 添加新日程 (针对补课和代课) ---
            if op_type in ('补课', '代课'):
                sub_teacher = tds[10]
                final_teacher = sub_teacher if (
                    op_type == '代课' and sub_teacher) else orig_teacher
                m_location = tds[9]

                affected_per_str = get_period_numbers(affected_per_str)

                for w in affected_weeks:
                    schedule_instances.append({
                        'course': f"{course_name}",
                        'teacher': final_teacher,
                        'week': w,
                        'day': affected_day,
                        'periods': affected_per_str,
                        'location': m_location,
                        'type': op_type,
                    })

    # 验证并转换每一个课程
    validated_instances = []
    for item in schedule_instances:
        try:
            s_t, e_t = get_period_time(item['periods'])
            item['start_time'] = s_t
            item['end_time'] = e_t

            # 计算该课程具体的日期
            days_offset = (item['week'] - 1) * 7 + (item['day'] - 1)
            target_date = week_1_monday + timedelta(days=days_offset)
            date = target_date.strftime('%Y-%m-%d')
            item['date'] = date

            validated_instances.append(CourseInstance(**item))
        except ValidationError as e:
            print(f"解析条目失败: {e}")

    # 返回封装好的整体模型
    return ScheduleSchema(
        student_id=student_id,
        student_name=student_name,
        academic_year=academic_year,
        semester=semester,
        week_1_monday=week_1_monday,
        instances=validated_instances
    )
