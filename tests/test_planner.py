from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from models import ProjectRule, ProjectSubfolderRule, Ruleset, ScannedFile, SpecialCategoryRule
from services.planner import PlannerService


class PlannerServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ruleset = Ruleset(
            projects=[
                ProjectRule(name="泗泾J项目", keywords=["泗泾", "J项目"], folder="01_泗泾J项目"),
            ],
            file_types={"PDF文档": ["pdf"], "Office文档": ["xlsx"]},
            special_categories=[
                SpecialCategoryRule(folder="98_AI新闻资讯", keywords=["AI"], extensions=["pdf"]),
            ],
            misc_folder="90_零散文件",
            other_subfolder="其他文件",
        )
        self.planner = PlannerService()

    def _make_file(self, relative_path: str, month_tag: str = "") -> ScannedFile:
        path = Path("J:/source") / relative_path
        return ScannedFile(
            source_path=path,
            relative_path=relative_path,
            name=path.name,
            stem=path.stem,
            extension=path.suffix.lower().strip("."),
            size=10,
            modified_at=datetime(2026, 3, 24, 10, 0, 0),
            month_tag=month_tag,
        )

    def test_project_has_priority_over_special_category(self) -> None:
        plan = self.planner.build_plan(
            [self._make_file("2020-03/泗泾J项目/AI周报.pdf", month_tag="2020-03")],
            self.ruleset,
            add_month_prefix=True,
        )
        item = plan.items[0]
        self.assertEqual(item.top_folder, "01_泗泾J项目")
        self.assertEqual(item.sub_folder, "")
        self.assertEqual(item.target_name, "2020-03_AI周报.pdf")
        self.assertEqual(item.category_source, "project")

    def test_special_category_without_enabled_subfolders_does_not_use_file_type_folder(self) -> None:
        plan = self.planner.build_plan(
            [self._make_file("2020-03/AI周报.pdf", month_tag="2020-03")],
            self.ruleset,
            add_month_prefix=True,
        )
        item = plan.items[0]
        self.assertEqual(item.top_folder, "98_AI新闻资讯")
        self.assertEqual(item.sub_folder, "")
        self.assertEqual(item.category_source, "special")

    def test_misc_is_used_when_no_rule_matches(self) -> None:
        plan = self.planner.build_plan(
            [self._make_file("其他资料/清单.xlsx")],
            self.ruleset,
            add_month_prefix=True,
        )
        item = plan.items[0]
        self.assertEqual(item.top_folder, "90_零散文件")
        self.assertEqual(item.sub_folder, "Office文档")
        self.assertEqual(item.category_source, "misc")

    def test_project_subfolder_rule_overrides_file_type_subfolder(self) -> None:
        self.ruleset.projects[0].subfolders = [
            ProjectSubfolderRule(name="报批文件", keywords=["报批"], extensions=["pdf"]),
        ]
        plan = self.planner.build_plan(
            [self._make_file("2020-03/泗泾J项目/报批文本.pdf", month_tag="2020-03")],
            self.ruleset,
            add_month_prefix=True,
        )
        item = plan.items[0]
        self.assertEqual(item.top_folder, "01_泗泾J项目")
        self.assertEqual(item.sub_folder, "报批文件")
        self.assertEqual(item.category_source, "project")


if __name__ == "__main__":
    unittest.main()
