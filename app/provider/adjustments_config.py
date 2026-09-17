"""Loading and validation for the holiday-adjustments configuration."""

import json
from pathlib import Path
from typing import Any


class AdjustmentsConfigError(ValueError):
    """Raised when the adjustments file cannot be read or validated."""


def load_adjustments_config(path: Path) -> dict[str, Any]:
    """Load an adjustments JSON object from *path*."""
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise AdjustmentsConfigError(str(exc)) from exc

    if not isinstance(data, dict):
        raise AdjustmentsConfigError("顶层 JSON 必须是对象")
    return data
