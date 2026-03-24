from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

import requests

from models import (
    ProjectRule,
    ProjectSubfolderRule,
    Ruleset,
    SpecialCategoryRule,
    SpecialSubfolderRule,
)
from paths import API_CONFIG_PATH, API_CONFIG_TEMPLATE_PATH
from services.rules import RuleRepository


DEFAULT_API_CONFIG = {
    "provider": "openai",
    "api_key": "",
    "url": "",
    "model": "",
    "headers_template": "Bearer",
    "temperature": 0.3,
    "timeout": 90,
    "enabled": True,
}


class AIRulesError(RuntimeError):
    pass


class AIRulesService:
    def __init__(
        self,
        api_config_path: Path = API_CONFIG_PATH,
        api_template_path: Path = API_CONFIG_TEMPLATE_PATH,
    ) -> None:
        self.api_config_path = api_config_path
        self.api_template_path = api_template_path

    def ensure_api_config(self) -> Path:
        if self.api_config_path.exists():
            return self.api_config_path
        payload = DEFAULT_API_CONFIG
        if self.api_template_path.exists():
            payload = json.loads(self.api_template_path.read_text(encoding="utf-8"))
        self.api_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.api_config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.api_config_path

    def load_api_config(self) -> dict:
        self.ensure_api_config()
        return json.loads(self.api_config_path.read_text(encoding="utf-8"))

    def suggest_rules(
        self,
        scanned_paths: list[str],
        existing_rules: Ruleset,
        user_request: str = "",
        conversation_history: list[tuple[str, str]] | None = None,
        reset_existing_results: bool = False,
    ) -> Ruleset:
        config = self.load_api_config()
        if not config.get("enabled", True):
            raise AIRulesError("当前 API 配置已禁用，请先在配置文件中启用。")
        if not config.get("api_key"):
            raise AIRulesError(f"请先填写 API 密钥：{self.api_config_path}")
        if not config.get("url"):
            raise AIRulesError(f"请先填写 API 地址：{self.api_config_path}")
        if not config.get("model"):
            raise AIRulesError(f"请先填写模型名称：{self.api_config_path}")

        cleaned_rules = self.build_seed_rules(
            existing_rules,
            reset_existing_results=reset_existing_results,
        )
        prompt = self._build_prompt(
            scanned_paths=scanned_paths,
            existing_rules=cleaned_rules,
            user_request=user_request,
            conversation_history=conversation_history or [],
        )
        content = self._request_completion(config, prompt)
        payload = self._extract_json(content)
        return self._merge_rules(cleaned_rules, payload)

    def build_seed_rules(self, existing_rules: Ruleset, reset_existing_results: bool = False) -> Ruleset:
        if reset_existing_results:
            return Ruleset(
                projects=[],
                file_types=deepcopy(existing_rules.file_types),
                special_categories=[],
                misc_folder=existing_rules.misc_folder,
                other_subfolder=existing_rules.other_subfolder,
            )
        return self._strip_template_projects(existing_rules)

    def _build_prompt(
        self,
        scanned_paths: list[str],
        existing_rules: Ruleset,
        user_request: str,
        conversation_history: list[tuple[str, str]],
    ) -> str:
        sample_lines = "\n".join(f"- {path}" for path in scanned_paths[:200])
        project_lines = "\n".join(
            f"- {item.name} | 目录: {item.folder} | 关键词: {', '.join(item.keywords) or '无'}"
            for item in existing_rules.projects[:40]
        )
        special_lines = "\n".join(
            f"- {item.folder} | 关键词: {', '.join(item.keywords) or '无'} | 扩展名: {', '.join(item.extensions) or '无'}"
            for item in existing_rules.special_categories[:40]
        )
        conversation_lines = "\n".join(
            f"{role}: {message}" for role, message in conversation_history[-8:] if message.strip()
        )
        return (
            "你是一名中文文件整理规则助手，需要为本地文件整理工具生成可落地的分类规则。\n"
            "请严格遵守下面的规则：\n"
            "1. 项目分类优先，先识别明确项目，再补充特殊分类，最后才归入零散文件。\n"
            "2. 特殊分类只是补充层，不能抢占本来应该归到项目目录的文件。\n"
            "3. 零散文件不能伪造为独立项目。\n"
            "4. 如果用户是在已有规则基础上要求合并、拆分、改名或追加分类，请保留未被点名修改的现有结构。\n"
            "5. 输出必须是 JSON，不要附加解释文本。\n"
            "6. JSON 结构固定如下：\n"
            "{\n"
            '  "projects": [\n'
            '    {\n'
            '      "name": "项目名称",\n'
            '      "keywords": ["关键词"],\n'
            '      "folder": "01_项目名称",\n'
            '      "enable_subfolders": true,\n'
            '      "subfolders": [{"name": "报批文件", "keywords": ["报批"], "extensions": ["pdf"]}]\n'
            "    }\n"
            "  ],\n"
            '  "special_categories": [\n'
            '    {\n'
            '      "folder": "98_AI新闻资讯",\n'
            '      "keywords": ["AI"],\n'
            '      "extensions": ["pdf"],\n'
            '      "pattern": "",\n'
            '      "enable_subfolders": true,\n'
            '      "subfolders": [{"name": "日报", "keywords": ["日报"], "extensions": ["pdf"]}]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "当前已有项目规则：\n"
            f"{project_lines or '- 无'}\n\n"
            "当前已有特殊分类：\n"
            f"{special_lines or '- 无'}\n\n"
            "最近几轮对话上下文：\n"
            f"{conversation_lines or '- 无'}\n\n"
            "待分析文件样本：\n"
            f"{sample_lines or '- 无文件'}\n\n"
            "本轮用户要求：\n"
            f"{user_request or '请基于当前样本生成一版更合理的分类规则。'}\n"
        )

    def _request_completion(self, config: dict, prompt: str) -> str:
        provider = str(config.get("provider", "")).lower()
        headers_template = str(config.get("headers_template", "Bearer")).lower()
        if provider == "anthropic" or headers_template == "anthropic":
            return self._request_anthropic(config, prompt)
        if provider == "qwen":
            return self._request_qwen(config, prompt)
        return self._request_openai_compatible(config, prompt)

    def _request_openai_compatible(self, config: dict, prompt: str) -> str:
        url = self._normalize_url(config)
        headers = self._build_headers(config)
        try:
            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": config["model"],
                    "temperature": config.get("temperature", 0.3),
                    "messages": [
                        {"role": "system", "content": "你只返回 JSON。"},
                        {"role": "user", "content": prompt},
                    ],
                },
                timeout=config.get("timeout", 90),
            )
        except requests.exceptions.ReadTimeout as exc:
            raise AIRulesError(
                f"AI 请求超时：{url}。当前 timeout={config.get('timeout', 90)} 秒，可以在 API 设置里调大 timeout 后再试。"
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise AIRulesError(self._format_ssl_error(config, exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise AIRulesError(f"AI 请求失败：{exc}") from exc
        response.raise_for_status()
        payload = response.json()
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIRulesError(f"AI 返回格式无法识别：{exc}") from exc

    def _request_qwen(self, config: dict, prompt: str) -> str:
        headers = self._build_headers(config)
        url = self._normalize_url(config)
        try:
            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": config["model"],
                    "input": {"messages": [{"role": "user", "content": prompt}]},
                    "parameters": {"temperature": config.get("temperature", 0.3), "max_tokens": 4000},
                },
                timeout=config.get("timeout", 90),
            )
        except requests.exceptions.ReadTimeout as exc:
            raise AIRulesError(
                f"AI 请求超时：{url}。当前 timeout={config.get('timeout', 90)} 秒，可以在 API 设置里调大 timeout 后再试。"
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise AIRulesError(self._format_ssl_error(config, exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise AIRulesError(f"AI 请求失败：{exc}") from exc
        response.raise_for_status()
        payload = response.json()
        try:
            return payload["output"]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIRulesError(f"AI 返回格式无法识别：{exc}") from exc

    def _request_anthropic(self, config: dict, prompt: str) -> str:
        headers = {
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        url = str(config.get("url", "")).strip()
        try:
            response = requests.post(
                url,
                headers=headers,
                json={
                    "model": config["model"],
                    "temperature": config.get("temperature", 0.3),
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=config.get("timeout", 90),
            )
        except requests.exceptions.ReadTimeout as exc:
            raise AIRulesError(
                f"AI 请求超时：{url}。当前 timeout={config.get('timeout', 90)} 秒，可以在 API 设置里调大 timeout 后再试。"
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise AIRulesError(self._format_ssl_error(config, exc)) from exc
        except requests.exceptions.RequestException as exc:
            raise AIRulesError(f"AI 请求失败：{exc}") from exc
        response.raise_for_status()
        payload = response.json()
        try:
            blocks = payload["content"]
            return "".join(block["text"] for block in blocks if block.get("type") == "text")
        except (KeyError, IndexError, TypeError) as exc:
            raise AIRulesError(f"AI 返回格式无法识别：{exc}") from exc

    def _extract_json(self, content: str) -> dict:
        stripped = content.strip()
        match = re.search(r"```json\s*(\{.*\})\s*```", stripped, re.S)
        if match:
            stripped = match.group(1)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AIRulesError(f"AI 返回内容不是合法 JSON：{exc}") from exc

    def _normalize_url(self, config: dict) -> str:
        provider = str(config.get("provider", "")).lower()
        url = str(config.get("url", "")).strip()
        if provider == "custom" and url:
            return self._ensure_url_endpoint(url)
        if provider == "deepseek" and not url:
            return "https://api.deepseek.com/v1/chat/completions"
        if provider == "openai" and not url:
            return "https://api.openai.com/v1/chat/completions"
        if provider == "qwen" and not url:
            return "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation"
        if provider == "claude" and not url:
            return "https://api.anthropic.com/v1/messages"
        return url

    def _build_headers(self, config: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = str(config.get("api_key", "")).strip()
        template = str(config.get("headers_template", "Bearer")).strip()
        if template == "api-key":
            headers["x-api-key"] = api_key
        elif template == "Token":
            headers["Authorization"] = f"Token {api_key}"
        else:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _ensure_url_endpoint(self, url: str) -> str:
        normalized = url.strip()
        if not normalized:
            return normalized
        if normalized.endswith("/chat/completions") or normalized.endswith("/messages"):
            return normalized
        if normalized.endswith("/v1"):
            return normalized + "/chat/completions"
        return normalized.rstrip("/") + "/v1/chat/completions"

    def _format_ssl_error(self, config: dict, exc: Exception) -> str:
        url = str(config.get("url", "")).strip()
        headers_template = str(config.get("headers_template", "Bearer")).strip()
        message = f"AI 请求失败：{exc}"
        if "coding.dashscope.aliyuncs.com" in url:
            message += (
                "\n\n当前是 DashScope 兼容接口地址。"
                f"你现在配置的认证方式是 {headers_template}。"
                "如果持续出现 SSL EOF，可以在 API 设置里手动切换认证方式后再测一次连通性。"
            )
        return message

    def _merge_rules(self, existing_rules: Ruleset, payload: dict) -> Ruleset:
        rules = deepcopy(existing_rules)
        if "projects" in payload:
            projects: list[ProjectRule] = []
            for index, item in enumerate(payload.get("projects", []), start=1):
                name = str(item.get("name", "")).strip()
                if not name:
                    continue
                folder = str(item.get("folder", "")).strip() or f"{index:02d}_{name}"
                projects.append(
                    ProjectRule(
                        name=name,
                        keywords=[str(value).strip() for value in item.get("keywords", []) if str(value).strip()],
                        folder=folder,
                        enable_subfolders=bool(item.get("enable_subfolders", False)),
                        subfolders=[
                            ProjectSubfolderRule(
                                name=str(subfolder.get("name", "")).strip(),
                                keywords=[str(value).strip() for value in subfolder.get("keywords", []) if str(value).strip()],
                                extensions=[
                                    str(value).lower().strip(". ")
                                    for value in subfolder.get("extensions", [])
                                    if str(value).strip()
                                ],
                            )
                            for subfolder in item.get("subfolders", [])
                            if str(subfolder.get("name", "")).strip()
                        ],
                    )
                )
            if projects:
                rules.projects = projects

        if "special_categories" in payload:
            categories: list[SpecialCategoryRule] = []
            for item in payload.get("special_categories", []):
                folder = str(item.get("folder", "")).strip()
                if not folder:
                    continue
                categories.append(
                    SpecialCategoryRule(
                        folder=folder,
                        keywords=[str(value).strip() for value in item.get("keywords", []) if str(value).strip()],
                        extensions=[
                            str(value).lower().strip(". ")
                            for value in item.get("extensions", [])
                            if str(value).strip()
                        ],
                        pattern=str(item.get("pattern", "")).strip(),
                        enable_subfolders=bool(item.get("enable_subfolders", False)),
                        subfolders=[
                            SpecialSubfolderRule(
                                name=str(subfolder.get("name", "")).strip(),
                                keywords=[str(value).strip() for value in subfolder.get("keywords", []) if str(value).strip()],
                                extensions=[
                                    str(value).lower().strip(". ")
                                    for value in subfolder.get("extensions", [])
                                    if str(value).strip()
                                ],
                            )
                            for subfolder in item.get("subfolders", [])
                            if str(subfolder.get("name", "")).strip()
                        ],
                    )
                )
            rules.special_categories = categories
        return rules

    def _strip_template_projects(self, ruleset: Ruleset) -> Ruleset:
        cleaned = deepcopy(ruleset)
        cleaned.projects = [project for project in cleaned.projects if not self._looks_like_template_project(project)]
        return cleaned

    def _looks_like_template_project(self, project: ProjectRule) -> bool:
        markers = ("示例",)
        if any(marker in project.name for marker in markers):
            return True
        if any(marker in project.folder for marker in markers):
            return True
        return False


def save_rules_via_repository(ruleset: Ruleset, repository: RuleRepository | None = None) -> Path:
    repo = repository or RuleRepository()
    return repo.save_generated_rules(ruleset)
