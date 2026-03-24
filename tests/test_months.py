from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.months import normalize_month_component, resolve_month_tag


class MonthParsingTests(unittest.TestCase):
    def test_normalize_year_month_formats(self) -> None:
        self.assertEqual(normalize_month_component("2020-03"), "2020-03")
        self.assertEqual(normalize_month_component("2020.3"), "2020-03")
        self.assertEqual(normalize_month_component("202003"), "2020-03")
        self.assertEqual(normalize_month_component("2020年3月"), "2020-03")
        self.assertEqual(normalize_month_component("03月"), "03月")

    def test_resolve_month_tag_from_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "微信文件" / "2020年3月" / "项目A" / "资料.pdf"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("demo", encoding="utf-8")
            self.assertEqual(resolve_month_tag(target, root), "2020-03")

    def test_resolve_month_tag_when_source_root_itself_is_month_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "2025-07"
            root.mkdir(parents=True, exist_ok=True)
            target = root / "图纸.dwg"
            target.write_text("demo", encoding="utf-8")
            self.assertEqual(resolve_month_tag(target, root), "2025-07")


if __name__ == "__main__":
    unittest.main()
