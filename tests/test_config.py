import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import PROJECT_ROOT, get_adjustments_path
from app.provider.adjustments_config import (
    AdjustmentsConfigError,
    load_adjustments_config,
)


class AdjustmentsPathTests(unittest.TestCase):
    def test_defaults_to_project_root(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                get_adjustments_path(), PROJECT_ROOT / "adjustments.json"
            )

    def test_relative_path_is_resolved_from_project_root(self):
        with patch.dict(
            os.environ,
            {"ADJUSTMENTS_PATH": "config/adjustments.json"},
            clear=True,
        ):
            self.assertEqual(
                get_adjustments_path(),
                (PROJECT_ROOT / "config/adjustments.json").resolve(),
            )

    def test_absolute_path_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adjustments.json"
            with patch.dict(
                os.environ, {"ADJUSTMENTS_PATH": str(path)}, clear=True
            ):
                self.assertEqual(get_adjustments_path(), path.resolve())


class AdjustmentsConfigTests(unittest.TestCase):
    def test_loads_json_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adjustments.json"
            path.write_text('{"holiday": {"days_suspend": []}}', encoding="utf-8")

            self.assertEqual(
                load_adjustments_config(path),
                {"holiday": {"days_suspend": []}},
            )

    def test_rejects_non_object_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adjustments.json"
            path.write_text("[]", encoding="utf-8")

            with self.assertRaisesRegex(
                AdjustmentsConfigError, "顶层 JSON 必须是对象"
            ):
                load_adjustments_config(path)

    def test_missing_file_remains_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_adjustments_config(Path("definitely-missing-adjustments.json"))


if __name__ == "__main__":
    unittest.main()
