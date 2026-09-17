import json
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config.json"


def get_adjustments_path() -> Path:
    """Return the configured holiday-adjustments file path.

    Relative paths from ``ADJUSTMENTS_PATH`` are resolved from the project root,
    rather than from the process working directory. This keeps CLI, container,
    editable-install, and service-manager launches consistent.
    """
    configured_path = os.getenv("ADJUSTMENTS_PATH")
    if not configured_path:
        return PROJECT_ROOT / "adjustments.json"

    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@lru_cache(maxsize=1)
def get_config() -> Dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
        return json.load(config_file)


def next_curriculum_enabled() -> bool:
    return get_config().get("next_curriculum", {}).get("enabled") is True


def get_next_curriculum_week_1_monday() -> datetime:
    value = get_config().get("next_curriculum", {}).get("week_1_monday")
    if not isinstance(value, str):
        raise ValueError("config.json 缺少 next_curriculum.week_1_monday")
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            "next_curriculum.week_1_monday 必须为 YYYY-MM-DD 格式"
        ) from exc
