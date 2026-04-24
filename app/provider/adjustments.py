import json
import os
from datetime import datetime
from app.schemas.schemas import ScheduleSchema


def apply_holiday_adjustments(schedule: ScheduleSchema) -> ScheduleSchema:
    """
    根据 adjustments.json 应用调休逻辑
    1. days_suspend: 列表中的日期，所有课程类型改为“调休”
    2. days_mapping: 映射关系，如 {"2026-05-09": "2026-05-04"}，
       表示 5月9日（目标）上 5月4日（源）的课。
       目标日期的原有课程会被移除，源日期的课程会复制到目标日期，且类型改为“调休”。
    """
    # 允许从环境变量或当前目录读取
    base_path = os.getcwd()
    adjust_file = os.path.join(base_path, "adjustments.json")

    if not os.path.exists(adjust_file):
        return schedule

    try:
        with open(adjust_file, "r", encoding="utf-8") as f:
            adjustments = json.load(f)
    except Exception as e:
        # 可以考虑使用 logging
        print(f"Error loading adjustments.json: {e}")
        return schedule

    all_suspend_dates = set()
    mapping_configs = {}  # target_date -> source_date

    for holiday_config in adjustments.values():
        if not isinstance(holiday_config, dict):
            continue
        suspend_dates = holiday_config.get("days_suspend", [])
        if isinstance(suspend_dates, list):
            all_suspend_dates.update(suspend_dates)

        mapping = holiday_config.get("days_mapping", {})
        if isinstance(mapping, dict):
            mapping_configs.update(mapping)

    # 1. 处理 mapping (换课/补课)
    additional_instances = []
    target_dates_to_clear = set(mapping_configs.keys())

    # 获取 week_1_monday (移除时区信息以便比较)
    w1m = schedule.week_1_monday
    if w1m.tzinfo:
        w1m = w1m.replace(tzinfo=None)

    for target_date, source_date in mapping_configs.items():
        # 找到 source_date 的所有课
        source_insts = [inst for inst in schedule.instances if inst.date == source_date]

        if not source_insts:
            continue

        try:
            target_dt = datetime.strptime(target_date, "%Y-%m-%d")
            target_dt = target_dt.replace(hour=0, minute=0, second=0, microsecond=0)

            # 计算相对于 week_1_monday 的偏移
            delta = target_dt - w1m

            target_week = (delta.days // 7) + 1
            target_day = (delta.days % 7) + 1

            for s_inst in source_insts:
                new_inst = s_inst.model_copy()
                new_inst.date = target_date
                new_inst.week = target_week
                new_inst.day = target_day
                new_inst.type = "常规"
                # 在描述中补充说明
                source_note = f"【调休补课】由 {source_date} 调至此处"
                if new_inst.description:
                    new_inst.description = f"{source_note}\\n{new_inst.description}"
                else:
                    new_inst.description = source_note

                additional_instances.append(new_inst)
        except Exception as e:
            print(f"Error processing mapping {source_date} -> {target_date}: {e}")

    # 2. 统一过滤：删除掉所有放假日期 (suspend) 和 补课目标日期原本的课程 (clear)
    dates_to_remove = all_suspend_dates.union(target_dates_to_clear)

    schedule.instances = [
        inst for inst in schedule.instances if inst.date not in dates_to_remove
    ]

    # 3. 将新增的调休补课日程加入
    schedule.instances.extend(additional_instances)

    return schedule
