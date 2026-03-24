from __future__ import annotations

import unittest

from models import ProjectRule, Ruleset, SpecialCategoryRule
from services.ai_rules import AIRulesService


class AIRulesServiceTests(unittest.TestCase):
    def test_build_prompt_includes_recent_conversation_history(self) -> None:
        service = AIRulesService()
        ruleset = Ruleset(
            projects=[ProjectRule(name="泗泾J项目", keywords=["泗泾"], folder="01_泗泾J项目")],
            file_types={"PDF文档": ["pdf"]},
            special_categories=[SpecialCategoryRule(folder="98_AI新闻资讯", keywords=["AI"], extensions=["pdf"])],
            misc_folder="90_零散文件",
            other_subfolder="其他文件",
        )

        prompt = service._build_prompt(
            scanned_paths=["2020-03/泗泾/AI周报.pdf"],
            existing_rules=ruleset,
            user_request="把 AI 资料并入泗泾J项目",
            conversation_history=[
                ("系统", "你可以先让 AI 生成规则。"),
                ("你", "先生成一版"),
                ("AI", "已生成初版规则"),
                ("你", "把 AI 资料并入泗泾J项目"),
            ],
        )

        self.assertIn("最近几轮对话上下文", prompt)
        self.assertIn("你: 把 AI 资料并入泗泾J项目", prompt)
        self.assertIn("AI: 已生成初版规则", prompt)
        self.assertIn("项目分类优先", prompt)

    def test_custom_provider_respects_selected_header_template(self) -> None:
        service = AIRulesService()
        config = {
            "provider": "custom",
            "api_key": "demo-key",
            "url": "https://coding.dashscope.aliyuncs.com/v1",
            "headers_template": "api-key",
        }

        self.assertEqual(
            service._normalize_url(config),
            "https://coding.dashscope.aliyuncs.com/v1/chat/completions",
        )
        headers = service._build_headers(config)
        self.assertEqual(headers["x-api-key"], "demo-key")
        self.assertEqual(headers["Content-Type"], "application/json")

    def test_build_seed_rules_can_clear_previous_projects_and_special_categories(self) -> None:
        service = AIRulesService()
        ruleset = Ruleset(
            projects=[ProjectRule(name="旧项目", keywords=["旧"], folder="01_旧项目")],
            file_types={"PDF文档": ["pdf"]},
            special_categories=[SpecialCategoryRule(folder="98_AI资讯", keywords=["AI"], extensions=["pdf"])],
            misc_folder="90_零散文件",
            other_subfolder="其他文件",
        )

        seed = service.build_seed_rules(ruleset, reset_existing_results=True)

        self.assertEqual(seed.projects, [])
        self.assertEqual(seed.special_categories, [])
        self.assertEqual(seed.file_types, ruleset.file_types)
        self.assertEqual(seed.misc_folder, "90_零散文件")
        self.assertEqual(seed.other_subfolder, "其他文件")


if __name__ == "__main__":
    unittest.main()
