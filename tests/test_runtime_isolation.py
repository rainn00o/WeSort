from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from paths import API_CONFIG_PATH, DEFAULT_RULES_PATH, GENERATED_RULES_PATH, LOGS_DIR, UI_STATE_PATH
from services.logging_utils import StepLogger
from services.rules import RuleRepository
from services.ui_state import UIStateRepository


class RuntimeIsolationTests(unittest.TestCase):
    def test_default_runtime_paths_are_inside_root_runtime_layout(self) -> None:
        self.assertEqual(DEFAULT_RULES_PATH.parent.name, "config")
        self.assertEqual(GENERATED_RULES_PATH.parent.name, "config")
        self.assertEqual(API_CONFIG_PATH.parent.name, "config")
        self.assertEqual(UI_STATE_PATH.parent.name, "config")
        self.assertEqual(LOGS_DIR.name, "logs")

    def test_repositories_can_write_to_custom_isolated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rules_path = root / "config" / "rules.json"
            generated_path = root / "config" / "rules_generated.json"
            state_path = root / "config" / "ui_state.json"
            log_root = root / "logs"
            rules_path.parent.mkdir(parents=True, exist_ok=True)
            rules_path.write_text(DEFAULT_RULES_PATH.read_text(encoding="utf-8"), encoding="utf-8")

            rules_repo = RuleRepository(default_rules_path=rules_path, generated_rules_path=generated_path)
            state_repo = UIStateRepository(path=state_path)
            logger = StepLogger(root_dir=log_root)

            rules = rules_repo.load_active_rules()
            saved_rules_path = rules_repo.save_generated_rules(rules)
            state_repo.save({"source_dir": "A", "target_dir": "B"})
            json_path, txt_path = logger.write("sample", {"value": 1})

            self.assertEqual(saved_rules_path, generated_path)
            self.assertTrue(generated_path.exists())
            self.assertTrue(state_path.exists())
            self.assertTrue(json_path.exists())
            self.assertTrue(txt_path.exists())

    def test_step_logger_can_write_structured_error_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = StepLogger(root_dir=Path(temp_dir) / "logs")
            json_path, txt_path = logger.write_error(
                "scan",
                RuntimeError("boom"),
                context={"source_dir": "J:/demo", "file_count": 3},
            )

            self.assertTrue(json_path.exists())
            self.assertTrue(txt_path.exists())
            payload = json_path.read_text(encoding="utf-8")
            self.assertIn('"step_name": "scan"', payload)
            self.assertIn('"error_type": "RuntimeError"', payload)
            self.assertIn('"source_dir": "J:/demo"', payload)


if __name__ == "__main__":
    unittest.main()
