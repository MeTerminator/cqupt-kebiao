import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from pydantic import ValidationError
from typing import Optional

from app.schemas.schemas import ScheduleSchema, CourseInstance
from app.provider.utils import weekday_to_date
from app.exceptions.JwzxError import JwzxError


# 课表 HTML 来源
# http://jwzx.cqupt.edu.cn/kebiao/kb_stu.php?xh=<学号>


def get_period_time(start_period, end_period):
    """根据起始节数和结束节数，计算起始和结束时间（每节45min，课间统一10min）"""
    # 每一节课对应的标准起始时间
    start_map = {
        1: "08:00", 2: "08:55", 3: "10:15", 4: "11:10",
        5: "14:00", 6: "14:55", 7: "16:15", 8: "17:10",
        9: "19:00", 10: "19:55", 11: "20:50", 12: "21:45",
    }
    try:
        start_str = start_map[start_period]
        # 计算总节数 (例如 1-3 节就是 3 节)
        count = end_period - start_period + 1

        # 计算总时长：每节 45 分钟 + 中间 (count-1) 个 10 分钟课间
        total_minutes = (count * 45) + ((count - 1) * 10)

        start_dt = datetime.strptime(start_str, "%H:%M")
        end_dt = start_dt + timedelta(minutes=total_minutes)

        return start_str, end_dt.strftime("%H:%M")
    except Exception:
        # 容错处理
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


def parse_jwzx_kebiao(html_content, request_at: Optional[datetime] = None) -> ScheduleSchema:
    soup = BeautifulSoup(html_content, 'html.parser')

    # 如果没传入时间（比如单测时），则使用当前时间
    if request_at is None:
        request_at = datetime.now()

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
        week_1_monday = request_at - \
            timedelta(days=request_at.weekday()) - \
            timedelta(weeks=(curr_w - 1))

        # 提取学号姓名
        stu_match = re.search(r'([L\d]\d{9})([\u4e00-\u9fa5]+)', head_text)
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

                    if "4节连上" in div.get_text():
                        start_p = int(re.findall(r'\d+', period_name)[0])
                        current_periods = f"{start_p}-{start_p+3}"

                    if "3节连上" in lines:
                        lines.remove("3节连上")

                    if "4节连上" in lines:
                        lines.remove("4节连上")

                    class_id = lines[0]
                    course_id, course_name = lines[1].split('-', 1)
                    location = lines[2].replace('地点：', '')
                    week_str = lines[3]

                    # 解析 教师 选必修类型 学分
                    parts = lines[4].split(' ')
                    teacher_parts = []
                    course_type = ""
                    credit = ""

                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue

                        # 1. 判断是否是选必修类型
                        if part in ["必修", "选修", "限选", "任选"]:
                            course_type = part

                        # 2. 判断是否包含学分（特征：包含“学分”二字）
                        elif "学分" in part:
                            # 提取数字部分，例如 "4.0学分" -> "4.0"
                            credit = part.replace("学分", "")

                        # 3. 过滤掉无用的后缀链接
                        elif "名单" in part or "查询" in part:
                            continue

                        # 4. 如果还没解析到类型和学分，且不是干扰项，则属于教师姓名
                        else:
                            # 只有在还没确定课程类型之前，才认为是老师名字
                            # 这样可以处理外教带空格的名字
                            if not course_type and not credit:
                                teacher_parts.append(part)

                    # 拼接教师姓名：外教用空格隔开，中文名拼接后也是正确的
                    teacher = " ".join(teacher_parts)

                    # 如果 teacher 为空（容错），设置默认值
                    if not teacher:
                        teacher = "未知教师"

                    current_periods = get_period_numbers(current_periods)

                    weeks = parse_week_string(week_str)
                    for w in weeks:
                        schedule_instances.append({
                            'course': course_name,
                            'course_id': course_id,
                            'class_id': class_id,
                            'course_type': course_type,
                            'credit': credit,
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

            # 用于保存被代课替换掉的原课程地点
            original_location = None

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

            affected_periods = get_period_numbers(affected_per_str)

            # --- 去重并捕获地点 ---
            new_schedule = []
            for inst in schedule_instances:
                inst_periods = get_period_numbers(inst['periods'])

                # 检查时间是否重合
                is_same_time = (inst['week'] in affected_weeks and
                                inst['day'] == affected_day and
                                any(p in inst_periods for p in affected_periods))

                # 如果时间冲突
                if is_same_time:
                    # 如果是代课，且找到了原课程，记录下它的地点
                    # 此处不需要判断是否是同一门课，如原课程为 体育1（上）羽毛球1班，代课课程可能为 大学体育1（上）
                    if op_type == '代课':  # and (course_name in inst['course']):
                        original_location = inst['location']

                    # 确定要删除/替换该项
                    if op_type == '停课':
                        if course_name in inst['course']:
                            continue
                    elif op_type in ('代课', '补课'):
                        continue

                new_schedule.append(inst)

            schedule_instances = new_schedule

            # --- 添加新日程 ---
            if op_type in ('补课', '代课'):
                sub_teacher = tds[10]
                final_teacher = sub_teacher if (
                    op_type == '代课' and sub_teacher) else orig_teacher

                # 如果是代课且我们抓到了原地点，就用原地点；否则用调停课表里的地点
                m_location = tds[9]
                if op_type == '代课' and original_location:
                    m_location = original_location

                affected_per_str_nums = get_period_numbers(affected_per_str)

                for w in affected_weeks:
                    schedule_instances.append({
                        'course': f"{course_name}",
                        'teacher': final_teacher,
                        'week': w,
                        'day': affected_day,
                        'periods': affected_per_str_nums,
                        'location': m_location,
                        'type': op_type,
                    })

    # 验证并转换每一个课程
    validated_instances = []
    for item in schedule_instances:
        try:
            s_t, e_t = get_period_time(item['periods'][0], item['periods'][-1])
            item['start_time'] = s_t
            item['end_time'] = e_t

            # 计算该课程具体的日期
            item['date'] = weekday_to_date(
                item['week'], item['day'], week_1_monday)

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
