from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk

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


class APISettingsWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("API 设置")
        self.geometry("780x540")
        self.minsize(720, 480)

        self.service = AIRulesService()
        self.testing = False

        self.provider_var = tk.StringVar()
        self.api_key_var = tk.StringVar()
        self.url_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.headers_var = tk.StringVar()
        self.temperature_var = tk.StringVar()
        self.timeout_var = tk.StringVar()
        self.enabled_var = tk.BooleanVar(value=True)
        self.show_key_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value=f"配置文件位置：{API_CONFIG_PATH}")

        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        outer = ttk.Frame(self, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(1, weight=1)

        row = 0
        ttk.Label(outer, text="API 提供商").grid(row=row, column=0, sticky="w")
        provider_combo = ttk.Combobox(
            outer,
            state="readonly",
            textvariable=self.provider_var,
            values=list(PRESET_PROVIDERS.keys()),
        )
        provider_combo.grid(row=row, column=1, sticky="ew", pady=(0, 8))
        provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_provider_state())

        row += 1
        ttk.Label(outer, text="API 密钥").grid(row=row, column=0, sticky="w")
        key_frame = ttk.Frame(outer)
        key_frame.grid(row=row, column=1, sticky="ew", pady=(0, 8))
        key_frame.columnconfigure(0, weight=1)
        self.api_key_entry = ttk.Entry(key_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(key_frame, text="显示", variable=self.show_key_var, command=self._toggle_key_visibility).grid(
            row=0, column=1, padx=(8, 0)
        )

        row += 1
        ttk.Label(outer, text="API 地址").grid(row=row, column=0, sticky="w")
        self.url_entry = ttk.Entry(outer, textvariable=self.url_var)
        self.url_entry.grid(row=row, column=1, sticky="ew", pady=(0, 8))

        row += 1
        ttk.Label(outer, text="模型名称").grid(row=row, column=0, sticky="w")
        self.model_entry = ttk.Entry(outer, textvariable=self.model_var)
        self.model_entry.grid(row=row, column=1, sticky="ew", pady=(0, 8))

        row += 1
        ttk.Label(outer, text="认证方式").grid(row=row, column=0, sticky="w")
        self.headers_combo = ttk.Combobox(
            outer,
            state="readonly",
            textvariable=self.headers_var,
            values=["Bearer", "api-key", "Token"],
        )
        self.headers_combo.grid(row=row, column=1, sticky="ew", pady=(0, 8))

        row += 1
        advanced = ttk.Frame(outer)
        advanced.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        advanced.columnconfigure(1, weight=1)
        advanced.columnconfigure(3, weight=1)
        ttk.Label(advanced, text="temperature").grid(row=0, column=0, sticky="w")
        ttk.Entry(advanced, textvariable=self.temperature_var).grid(row=0, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(advanced, text="timeout").grid(row=0, column=2, sticky="w")
        ttk.Entry(advanced, textvariable=self.timeout_var).grid(row=0, column=3, sticky="ew", padx=(8, 0))

        row += 1
        ttk.Checkbutton(outer, text="启用 AI 规则建议", variable=self.enabled_var).grid(
            row=row,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        row += 1
        self.info_label = ttk.Label(outer, justify=tk.LEFT)
        self.info_label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(0, 12))

        row += 1
        ttk.Label(outer, textvariable=self.status_var, justify=tk.LEFT).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )

        row += 1
        button_bar = ttk.Frame(outer)
        button_bar.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(button_bar, text="按预设填充", command=self._apply_provider_state).grid(row=0, column=0, padx=(0, 8))
        self.test_button = ttk.Button(button_bar, text="连通性测试", command=self._test_connection)
        self.test_button.grid(row=0, column=1, padx=(0, 8))
        ttk.Button(button_bar, text="保存", command=self._save).grid(row=0, column=2)

    def _toggle_key_visibility(self) -> None:
        self.api_key_entry.configure(show="" if self.show_key_var.get() else "*")

    def _load(self) -> None:
        payload = self.service.load_api_config()
        self.provider_var.set(str(payload.get("provider", "deepseek") or "deepseek"))
        self.api_key_var.set(str(payload.get("api_key", "")))
        self.url_var.set(str(payload.get("url", "")))
        self.model_var.set(str(payload.get("model", "")))
        self.headers_var.set(str(payload.get("headers_template", "Bearer") or "Bearer"))
        self.temperature_var.set(str(payload.get("temperature", 0.3)))
        self.timeout_var.set(str(payload.get("timeout", 90)))
        self.enabled_var.set(bool(payload.get("enabled", True)))
        self._apply_provider_state(keep_existing=True)

    def _apply_provider_state(self, keep_existing: bool = False) -> None:
        provider = self.provider_var.get() or "deepseek"
        preset = PRESET_PROVIDERS.get(provider, PRESET_PROVIDERS["custom"])
        custom = provider == "custom"
        if not keep_existing or not self.url_var.get().strip():
            self.url_var.set(preset["url"])
        if not keep_existing or not self.model_var.get().strip():
            self.model_var.set(preset["model"])
        if not keep_existing or not self.headers_var.get().strip():
            self.headers_var.set(preset["headers_template"])

        self.url_entry.configure(state="normal" if custom else "readonly")
        self.headers_combo.configure(state="readonly")
        self.info_label.configure(text=f"{preset['label']}：{preset['description']}")

    def _build_request(self) -> tuple[str, dict, dict, int]:
        provider = self.provider_var.get().strip() or "deepseek"
        api_key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        url = self.url_var.get().strip()
        headers_template = self.headers_var.get().strip() or "Bearer"
        timeout = int(self.timeout_var.get().strip() or "90")

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

    def _test_connection(self) -> None:
        if self.testing:
            return
        try:
            url, headers, payload, timeout = self._build_request()
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("API 设置", str(exc), parent=self)
            return

        self.testing = True
        self.test_button.state(["disabled"])
        self.status_var.set(f"正在测试：{url}")

        def worker() -> None:
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                self.after(0, lambda response=response: self._show_test_result(response, url))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda exc=exc, url=url: self._show_test_exception(exc, url))

        threading.Thread(target=worker, daemon=True).start()

    def _show_test_result(self, response: requests.Response, url: str) -> None:
        self.testing = False
        self.test_button.state(["!disabled"])
        self.status_var.set(f"测试完成：{url}")
        if response.status_code == 200:
            messagebox.showinfo("连通性测试", "API 连通正常。", parent=self)
        elif response.status_code == 401:
            messagebox.showerror("连通性测试", "API Key 无效或认证方式不对。", parent=self)
        elif response.status_code == 404:
            messagebox.showerror("连通性测试", "接口返回 404，请确认 URL 是否包含正确 endpoint。", parent=self)
        else:
            messagebox.showerror("连通性测试", f"状态码：{response.status_code}\n\n{response.text[:300]}", parent=self)

    def _show_test_exception(self, exc: Exception, url: str) -> None:
        self.testing = False
        self.test_button.state(["!disabled"])
        self.status_var.set(f"测试失败：{url}")
        if isinstance(exc, requests.exceptions.ReadTimeout):
            messagebox.showerror("连通性测试", f"请求超时：{exc}\n\n建议把 timeout 调大到 60 或 90 后再试。", parent=self)
            return
        if isinstance(exc, requests.exceptions.SSLError):
            messagebox.showerror(
                "连通性测试",
                (
                    f"SSL 握手失败：{exc}\n\n"
                    "这类错误常见于认证方式或服务端兼容模式不匹配。"
                    "对于 coding.dashscope.aliyuncs.com 的 OpenAI 兼容地址，建议使用 Bearer 认证。"
                ),
                parent=self,
            )
            return
        messagebox.showerror("连通性测试", f"请求失败：{exc}", parent=self)

    def _save(self) -> None:
        provider = self.provider_var.get().strip() or "deepseek"
        url = self.url_var.get().strip()
        if provider == "custom":
            url = _ensure_url_endpoint(url)
        elif not url:
            url = PRESET_PROVIDERS.get(provider, PRESET_PROVIDERS["deepseek"])["url"]

        headers_template = self.headers_var.get().strip() or "Bearer"

        try:
            payload = {
                "provider": provider,
                "api_key": self.api_key_var.get().strip(),
                "url": url,
                "model": self.model_var.get().strip(),
                "headers_template": headers_template,
                "temperature": float(self.temperature_var.get().strip() or "0.3"),
                "timeout": int(self.timeout_var.get().strip() or "90"),
                "enabled": self.enabled_var.get(),
                "_comment": "由当前 API 设置窗口保存。",
            }
        except ValueError:
            messagebox.showwarning("API 设置", "temperature 或 timeout 格式不正确。", parent=self)
            return

        path = self.service.ensure_api_config()
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.status_var.set(f"配置已保存：{path}")
        messagebox.showinfo("API 设置", f"配置已保存：\n{path}", parent=self)
