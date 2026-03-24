from __future__ import annotations

import tkinter as tk
import unittest
from datetime import datetime
from pathlib import Path

from gui.rule_editor_window import RuleEditorWindow
from models import ProjectRule, ProjectSubfolderRule, Ruleset, ScannedFile, SpecialCategoryRule, SpecialSubfolderRule


class RuleEditorWindowTests(unittest.TestCase):
    def _build_ruleset(self) -> Ruleset:
        return Ruleset(
            projects=[ProjectRule(name="泗泾J项目", keywords=["泗泾"], folder="01_泗泾J项目")],
            file_types={"PDF文档": ["pdf"], "Office文档": ["xlsx"]},
            special_categories=[
                SpecialCategoryRule(
                    folder="98_AI新闻资讯",
                    keywords=["AI"],
                    extensions=["pdf"],
                    subfolders=[
                        SpecialSubfolderRule(name="日报", keywords=["日报"], extensions=["pdf"]),
                    ],
                )
            ],
            misc_folder="90_零散文件",
            other_subfolder="其他文件",
        )

    def _build_scanned_files(self) -> list[ScannedFile]:
        return [
            ScannedFile(
                source_path=Path("J:/tmp/泗泾/技术核定单.pdf"),
                relative_path="2020-03/泗泾/技术核定单.pdf",
                name="技术核定单.pdf",
                stem="技术核定单",
                extension="pdf",
                size=1,
                modified_at=datetime.now(),
                month_tag="2020-03",
            ),
            ScannedFile(
                source_path=Path("J:/tmp/AI日报.pdf"),
                relative_path="2020-03/AI日报.pdf",
                name="AI日报.pdf",
                stem="AI日报",
                extension="pdf",
                size=1,
                modified_at=datetime.now(),
                month_tag="2020-03",
            ),
            ScannedFile(
                source_path=Path("J:/tmp/清单.xlsx"),
                relative_path="misc/清单.xlsx",
                name="清单.xlsx",
                stem="清单",
                extension="xlsx",
                size=1,
                modified_at=datetime.now(),
                month_tag="",
            ),
        ]

    def test_rule_editor_builds_preview_for_full_plan(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            dialog = RuleEditorWindow(root, self._build_ruleset(), self._build_scanned_files(), True, lambda rules: None)
            try:
                top_folders = {key[0] for key in dialog.preview_lookup.keys()}
                self.assertIn("01_泗泾J项目", top_folders)
                self.assertIn("98_AI新闻资讯", top_folders)
                self.assertIn("90_零散文件", top_folders)
                chat_text = dialog.chat_text.get("1.0", tk.END)
                self.assertIn("系统", chat_text)
                self.assertEqual(dialog.chat_history[0][0], "系统")
                self.assertIn("生成初版规则", dialog.preset_prompt_combo["values"])
            finally:
                dialog.destroy()
        finally:
            root.destroy()

    def test_special_subfolder_checkbox_disables_rule_creation_by_default(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            saved_rules: list[Ruleset] = []
            dialog = RuleEditorWindow(root, self._build_ruleset(), self._build_scanned_files(), True, saved_rules.append)
            try:
                dialog.special_list.selection_set(2)
                dialog._on_special_select()
                self.assertTrue(dialog.enable_special_subfolders_var.get())

                dialog.enable_special_subfolders_var.set(False)
                dialog._update_special_subfolder_editor_state()
                self.assertEqual(str(dialog.special_subfolders_text["state"]), "disabled")

                dialog._save_special()
                self.assertEqual(dialog.ruleset.special_categories[0].subfolders, [])
            finally:
                dialog.destroy()
        finally:
            root.destroy()

    def test_project_subfolder_checkbox_disables_rule_creation_by_default(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            ruleset = self._build_ruleset()
            ruleset.projects[0].subfolders = [
                ProjectSubfolderRule(name="报批文件", keywords=["报批"], extensions=["pdf"])
            ]
            dialog = RuleEditorWindow(root, ruleset, self._build_scanned_files(), True, lambda rules: None)
            try:
                dialog.project_list.selection_set(0)
                dialog._on_project_select()
                self.assertTrue(dialog.enable_project_subfolders_var.get())

                dialog.enable_project_subfolders_var.set(False)
                dialog._update_project_subfolder_editor_state()
                self.assertEqual(str(dialog.project_subfolders_text["state"]), "disabled")

                dialog._save_project()
                self.assertEqual(dialog.ruleset.projects[0].subfolders, [])
            finally:
                dialog.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
