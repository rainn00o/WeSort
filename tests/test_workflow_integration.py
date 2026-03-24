from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.duplicates import DuplicateService
from services.executor import ExecutorService
from services.planner import PlannerService
from services.rules import RuleRepository
from services.scanner import ScannerService


class WorkflowIntegrationTests(unittest.TestCase):
    def test_scan_duplicate_plan_execute_chain(self) -> None:
        scanner = ScannerService()
        duplicates = DuplicateService()
        planner = PlannerService()
        executor = ExecutorService()
        rules = RuleRepository().load_active_rules()

        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            root = Path(source_dir)
            month_dir = root / "wechat" / "2020-03" / "AI资料"
            month_dir.mkdir(parents=True, exist_ok=True)
            duplicate_a = month_dir / "2020.03.26_AI日报.pdf"
            duplicate_b = month_dir / "2020.03.26_AI日报(1).pdf"
            other_file = root / "misc" / "清单.xlsx"
            other_file.parent.mkdir(parents=True, exist_ok=True)
            duplicate_a.write_text("same", encoding="utf-8")
            duplicate_b.write_text("same", encoding="utf-8")
            other_file.write_text("sheet", encoding="utf-8")

            scanned = scanner.scan(root)
            self.assertEqual(len(scanned), 3)
            self.assertIn("2020-03", [item.month_tag for item in scanned])

            duplicate_result = duplicates.scan_duplicates([item.source_path for item in scanned])
            trash_result = duplicates.move_duplicates_to_trash(duplicate_result, Path(output_dir))
            self.assertEqual(trash_result.moved_count, 1)

            scanned = scanner.scan(root)
            plan = planner.build_plan(scanned, rules, add_month_prefix=True)
            self.assertEqual(len(plan.items), 2)
            self.assertTrue(any(item.target_name.startswith("2020-03_") for item in plan.items if item.source.month_tag))

            result = executor.execute(plan, Path(output_dir), generate_report=True)
            self.assertEqual(result.failed_count, 0)
            self.assertEqual(result.moved_count, 2)
            self.assertIsNotNone(result.report_json)
            self.assertIsNotNone(result.report_txt)
            self.assertTrue(result.report_json.exists())
            self.assertTrue(result.report_txt.exists())


if __name__ == "__main__":
    unittest.main()
