from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = PACKAGE_DIR / "config"
LOGS_DIR = PACKAGE_DIR / "logs"

DEFAULT_RULES_PATH = CONFIG_DIR / "rules.json"
GENERATED_RULES_PATH = CONFIG_DIR / "rules_generated.json"
API_CONFIG_PATH = CONFIG_DIR / "api_config.json"
API_CONFIG_TEMPLATE_PATH = CONFIG_DIR / "api_config.json.template"
UI_STATE_PATH = CONFIG_DIR / "ui_state.json"

