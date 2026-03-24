from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from models import PlanItem, PlanSummary, ScannedFile
from services.executor import ExecutorService


class ExecutorServiceTests(unittest.TestCase):
    def test_execute_moves_files_and_generates_reports(self) -> None:
        service = ExecutorService()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as output_dir:
            source = Path(source_dir) / "2020-03" / "日报.pdf"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("demo", encoding="utf-8")
            scanned = ScannedFile(
                source_path=source,
                relative_path="2020-03/日报.pdf",
                name="日报.pdf",
                stem="日报",
                extension="pdf",
                size=4,
                modified_at=datetime(2026, 3, 24, 10, 0, 0),
                month_tag="2020-03",
            )
            plan = PlanSummary(
                items=[
                    PlanItem(
                        source=scanned,
                        top_folder="98_AI新闻资讯",
                        sub_folder="PDF文档",
                        target_name="2020-03_日报.pdf",
                        category_source="special",
                        matched_rule="98_AI新闻资讯",
                        confidence=0.8,
                        reason="命中特殊分类",
                    )
                ]
            )

            result = service.execute(plan, Path(output_dir), generate_report=True)

            target = Path(output_dir) / "98_AI新闻资讯" / "PDF文档" / "2020-03_日报.pdf"
            self.assertTrue(target.exists())
            self.assertEqual(result.moved_count, 1)
            self.assertIsNone(result.report_json)
            self.assertIsNotNone(result.report_txt)
            self.assertTrue(result.report_txt.exists())


if __name__ == "__main__":
    unittest.main()
