"""PyQt6 API Settings dialog for WeSort."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import requests

from paths import API_CONFIG_PATH
from services.ai_rules import AIRulesService


PRESET_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "url": "https://api.deepseek.com/v1/chat/completions",
        "model": "deepseek-chat",
        "headers_template": "Bearer",
        "description": "国内访问方便，适合常规项目分析。",
    },
    "qwen": {
        "label": "通义千问",
        "url": "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
        "model": "qwen-turbo",
        "headers_template": "Bearer",
        "description": "阿里云官方接口。",
    },
    "claude": {
        "label": "Claude",
        "url": "https://api.anthropic.com/v1/messages",
        "model": "claude-3-haiku-20240307",
        "headers_template": "api-key",
        "description": "Anthropic 官方接口。",
    },
    "openai": {
        "label": "OpenAI",
        "url": "https://api.openai.com/v1/chat/completions",
        "model": "gpt-4o-mini",
        "headers_template": "Bearer",
        "description": "OpenAI 官方接口。",
    },
    "custom": {
        "label": "自定义",
        "url": "",
        "model": "",
        "headers_template": "Bearer",
        "description": "自定义 OpenAI 风格接口，支持自行填写 URL、模型和认证方式。",
    },
}


def _ensure_url_endpoint(url: str) -> str:
    normalized = url.strip()
    if not normalized:
        return normalized
    if normalized.endswith("/chat/completions") or normalized.endswith("/messages"):
        return normalized
    if normalized.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized.rstrip("/") + "/v1/chat/completions"


class TestConnectionThread(QThread):
    """Thread for testing API connection."""
    finished = pyqtSignal(object, str)  # response, url
    error = pyqtSignal(Exception, str)  # exception, url

    def __init__(self, url: str, headers: dict, payload: dict, timeout: int):
        super().__init__()
        self.url = url
        self.headers = headers
        self.payload = payload
        self.timeout = timeout

    def run(self):
        try:
            response = requests.post(
                self.url,
                headers=self.headers,
                json=self.payload,
                timeout=self.timeout
            )
            self.finished.emit(response, self.url)
        except Exception as e:
            self.error.emit(e, self.url)


class APISettingsDialog(QDialog):
    """API Settings dialog using PyQt6."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 设置")
        self.resize(650, 450)
        self.setMinimumSize(600, 400)

        self.service = AIRulesService()
        self.testing = False
        self.test_thread: TestConnectionThread | None = None

        self._build_ui()
        self._load()

    def _build_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Provider selection
        provider_group = QGroupBox("API 提供商")
        provider_layout = QVBoxLayout()
        provider_row = QWidget()
        provider_row_layout = QVBoxLayout()
        provider_row_layout.setContentsMargins(0, 0, 0, 0)

        self.provider_combo = QComboBox()
        self.provider_combo.addItems(list(PRESET_PROVIDERS.keys()))
        self.provider_combo.currentTextChanged.connect(self._apply_provider_state)
        provider_row_layout.addWidget(self.provider_combo)
        provider_row.setLayout(provider_row_layout)
        provider_layout.addWidget(provider_row)
        provider_group.setLayout(provider_layout)
        layout.addWidget(provider_group)

        # API Key
        key_group = QGroupBox("API 密钥")
        key_layout = QVBoxLayout()
        key_row = QWidget()
        key_row_layout = QVBoxLayout()
        key_row_layout.setContentsMargins(0, 0, 0, 0)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        key_row_layout.addWidget(self.api_key_edit)

        self.show_key_check = QCheckBox("显示")
        self.show_key_check.stateChanged.connect(self._toggle_key_visibility)
        key_row_layout.addWidget(self.show_key_check)

        key_row.setLayout(key_row_layout)
        key_layout.addWidget(key_row)
        key_group.setLayout(key_layout)
        layout.addWidget(key_group)

        # API URL
        url_group = QGroupBox("API 地址")
        url_layout = QVBoxLayout()
        self.url_edit = QLineEdit()
        url_layout.addWidget(self.url_edit)
        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # Model name
        model_group = QGroupBox("模型名称")
        model_layout = QVBoxLayout()
        self.model_edit = QLineEdit()
        model_layout.addWidget(self.model_edit)
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)

        # Auth method
        auth_group = QGroupBox("认证方式")
        auth_layout = QVBoxLayout()
        self.headers_combo = QComboBox()
        self.headers_combo.addItems(["Bearer", "api-key", "Token"])
        auth_layout.addWidget(self.headers_combo)
        auth_group.setLayout(auth_layout)
        layout.addWidget(auth_group)

        # Advanced settings
        advanced_group = QGroupBox("高级设置")
        advanced_layout = QFormLayout()
        self.temperature_edit = QLineEdit("0.3")
        self.timeout_edit = QLineEdit("90")
        advanced_layout.addRow("Temperature:", self.temperature_edit)
        advanced_layout.addRow("Timeout:", self.timeout_edit)
        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        # Enable AI
        self.enabled_check = QCheckBox("启用 AI 规则建议")
        self.enabled_check.setChecked(True)
        layout.addWidget(self.enabled_check)

        # Info label
        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #5B7FFF; font-size: 12px;")
        layout.addWidget(self.info_label)

        # Status label
        self.status_label = QLabel(f"配置文件位置：{API_CONFIG_PATH}")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #666666; font-size: 11px;")
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)

        self.apply_preset_button = QPushButton("按预设填充")
        self.apply_preset_button.clicked.connect(lambda: self._apply_provider_state())
        button_layout.addWidget(self.apply_preset_button)

        self.test_button = QPushButton("连通性测试")
        self.test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_button)

        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._save)
        button_layout.addWidget(self.save_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def _toggle_key_visibility(self, state):
        """Toggle API key visibility."""
        if state == Qt.CheckState.Checked.value:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _load(self):
        """Load API configuration."""
        payload = self.service.load_api_config()
        provider = payload.get("provider", "deepseek") or "deepseek"
        self.provider_combo.setCurrentText(str(provider))
        self.api_key_edit.setText(str(payload.get("api_key", "")))
        self.url_edit.setText(str(payload.get("url", "")))
        self.model_edit.setText(str(payload.get("model", "")))
        self.headers_combo.setCurrentText(str(payload.get("headers_template", "Bearer") or "Bearer"))
        self.temperature_edit.setText(str(payload.get("temperature", 0.3)))
        self.timeout_edit.setText(str(payload.get("timeout", 90)))
        self.enabled_check.setChecked(bool(payload.get("enabled", True)))
        self._apply_provider_state(keep_existing=True)

    def _apply_provider_state(self, keep_existing: bool = False):
        """Apply provider preset settings."""
        provider = self.provider_combo.currentText() or "deepseek"
        preset = PRESET_PROVIDERS.get(provider, PRESET_PROVIDERS["custom"])
        custom = provider == "custom"

        if not keep_existing or not self.url_edit.text().strip():
            self.url_edit.setText(preset["url"])
        if not keep_existing or not self.model_edit.text().strip():
            self.model_edit.setText(preset["model"])
        if not keep_existing or not self.headers_combo.currentText().strip():
            self.headers_combo.setCurrentText(preset["headers_template"])

        self.url_edit.setReadOnly(not custom)
        self.info_label.setText(f"{preset['label']}：{preset['description']}")

    def _build_request(self) -> tuple:
        """Build request parameters."""
        provider = self.provider_combo.currentText().strip() or "deepseek"
        api_key = self.api_key_edit.text().strip()
        model = self.model_edit.text().strip()
        url = self.url_edit.text().strip()
        headers_template = self.headers_combo.currentText().strip() or "Bearer"
        timeout = int(self.timeout_edit.text().strip() or "90")

        if not api_key:
            raise ValueError("请先填写 API 密钥。")
        if not model:
            raise ValueError("请先填写模型名称。")
        if provider == "custom":
            if not url:
                raise ValueError("请先填写 API 地址。")
            url = _ensure_url_endpoint(url)
        elif not url:
            url = PRESET_PROVIDERS.get(provider, PRESET_PROVIDERS["deepseek"])["url"]

        headers = {"Content-Type": "application/json"}
        if headers_template == "api-key":
            headers["x-api-key"] = api_key
        elif headers_template == "Token":
            headers["Authorization"] = f"Token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        if provider == "claude":
            headers["anthropic-version"] = "2023-06-01"
            payload = {
                "model": model,
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "ping"}],
            }
        elif provider == "qwen":
            payload = {
                "model": model,
                "input": {"messages": [{"role": "user", "content": "ping"}]},
                "parameters": {"max_tokens": 8},
            }
        else:
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 8,
            }

        return url, headers, payload, timeout

    def _test_connection(self):
        """Test API connection."""
        if self.testing:
            return

        try:
            url, headers, payload, timeout = self._build_request()
        except Exception as exc:
            QMessageBox.warning(self, "API 设置", str(exc))
            return

        self.testing = True
        self.test_button.setEnabled(False)
        self.status_label.setText(f"正在测试：{url}")

        self.test_thread = TestConnectionThread(url, headers, payload, timeout)
        self.test_thread.finished.connect(self._show_test_result)
        self.test_thread.error.connect(self._show_test_exception)
        self.test_thread.start()

    def _show_test_result(self, response: requests.Response, url: str):
        """Show test result."""
        self.testing = False
        self.test_button.setEnabled(True)
        self.status_label.setText(f"测试完成：{url}")

        if response.status_code == 200:
            QMessageBox.information(self, "连通性测试", "API 连通正常。")
        elif response.status_code == 401:
            QMessageBox.critical(self, "连通性测试", "API Key 无效或认证方式不对。")
        elif response.status_code == 404:
            QMessageBox.critical(self, "连通性测试", "接口返回 404，请确认 URL 是否包含正确 endpoint。")
        else:
            QMessageBox.critical(
                self, "连通性测试", f"状态码：{response.status_code}\n\n{response.text[:300]}"
            )

    def _show_test_exception(self, exc: Exception, url: str):
        """Show test exception."""
        self.testing = False
        self.test_button.setEnabled(True)
        self.status_label.setText(f"测试失败：{url}")

        if isinstance(exc, requests.exceptions.ReadTimeout):
            QMessageBox.critical(
                self, "连通性测试", f"请求超时：{exc}\n\n建议把 timeout 调大到 60 或 90 后再试。"
            )
        elif isinstance(exc, requests.exceptions.SSLError):
            QMessageBox.critical(
                self, "连通性测试",
                f"SSL 握手失败：{exc}\n\n这类错误常见于认证方式或服务端兼容模式不匹配。"
            )
        else:
            QMessageBox.critical(self, "连通性测试", f"请求失败：{exc}")

    def _save(self):
        """Save API configuration."""
        provider = self.provider_combo.currentText().strip() or "deepseek"
        url = self.url_edit.text().strip()
        if provider == "custom":
            url = _ensure_url_endpoint(url)
        elif not url:
            url = PRESET_PROVIDERS.get(provider, PRESET_PROVIDERS["deepseek"])["url"]

        headers_template = self.headers_combo.currentText().strip() or "Bearer"

        try:
            payload = {
                "provider": provider,
                "api_key": self.api_key_edit.text().strip(),
                "url": url,
                "model": self.model_edit.text().strip(),
                "headers_template": headers_template,
                "temperature": float(self.temperature_edit.text().strip() or "0.3"),
                "timeout": int(self.timeout_edit.text().strip() or "90"),
                "enabled": self.enabled_check.isChecked(),
                "_comment": "由当前 API 设置窗口保存。",
            }
        except ValueError:
            QMessageBox.warning(self, "API 设置", "temperature 或 timeout 格式不正确。")
            return

        path = self.service.ensure_api_config()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_label.setText(f"配置已保存：{path}")
        QMessageBox.information(self, "API 设置", f"配置已保存：\n{path}")
