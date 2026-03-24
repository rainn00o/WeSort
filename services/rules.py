from __future__ import annotations

import json
from pathlib import Path

from models import (
    ProjectRule,
    ProjectSubfolderRule,
    Ruleset,
    SpecialCategoryRule,
    SpecialSubfolderRule,
)
from paths import DEFAULT_RULES_PATH, GENERATED_RULES_PATH


class RuleRepository:
    def __init__(
        self,
        default_rules_path: Path = DEFAULT_RULES_PATH,
        generated_rules_path: Path = GENERATED_RULES_PATH,
    ) -> None:
        self.default_rules_path = default_rules_path
        self.generated_rules_path = generated_rules_path

    def load_active_rules(self) -> Ruleset:
        path = self.generated_rules_path if self.generated_rules_path.exists() else self.default_rules_path
        return self.load_from_path(path)

    def load_from_path(self, path: Path) -> Ruleset:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return self._from_payload(payload)

    def save_generated_rules(self, ruleset: Ruleset) -> Path:
        payload = self._to_payload(ruleset)
        self.generated_rules_path.parent.mkdir(parents=True, exist_ok=True)
        self.generated_rules_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self.generated_rules_path

    def _from_payload(self, payload: dict) -> Ruleset:
        projects = [
            ProjectRule(
                name=str(item.get("name", "")).strip(),
                keywords=[keyword.strip() for keyword in item.get("keywords", []) if str(keyword).strip()],
                folder=str(item.get("folder", "")).strip(),
                enable_subfolders=bool(item.get("enable_subfolders", False)),
                subfolders=[
                    ProjectSubfolderRule(
                        name=str(subfolder.get("name", "")).strip(),
                        keywords=[value.strip() for value in subfolder.get("keywords", []) if str(value).strip()],
                        extensions=[value.lower().strip(". ") for value in subfolder.get("extensions", []) if str(value).strip()],
                    )
                    for subfolder in item.get("subfolders", [])
                    if str(subfolder.get("name", "")).strip()
                ],
            )
            for item in payload.get("projects", [])
            if str(item.get("name", "")).strip() and str(item.get("folder", "")).strip()
        ]
        file_types = {
            folder.strip(): [extension.lower().strip(". ") for extension in extensions if str(extension).strip()]
            for folder, extensions in payload.get("file_types", {}).items()
        }

        special_categories: list[SpecialCategoryRule] = []
        raw_special_categories = payload.get("special_categories", {})
        for folder, config in raw_special_categories.items():
            special_categories.append(
                SpecialCategoryRule(
                    folder=str(folder).strip(),
                    keywords=[keyword.strip() for keyword in config.get("keywords", []) if str(keyword).strip()],
                    extensions=[value.lower().strip(". ") for value in config.get("extensions", []) if str(value).strip()],
                    pattern=str(config.get("pattern", "")).strip(),
                    enable_subfolders=bool(config.get("enable_subfolders", False)),
                    subfolders=[
                        SpecialSubfolderRule(
                            name=str(subfolder.get("name", "")).strip(),
                            keywords=[value.strip() for value in subfolder.get("keywords", []) if str(value).strip()],
                            extensions=[value.lower().strip(". ") for value in subfolder.get("extensions", []) if str(value).strip()],
                        )
                        for subfolder in config.get("subfolders", [])
                        if str(subfolder.get("name", "")).strip()
                    ],
                )
            )

        return Ruleset(
            projects=projects,
            file_types=file_types,
            special_categories=special_categories,
            misc_folder=str(payload.get("misc_folder", "90_零散文件")).strip() or "90_零散文件",
            other_subfolder=str(payload.get("other_subfolder", "其他文件")).strip() or "其他文件",
        )

    def _to_payload(self, ruleset: Ruleset) -> dict:
        return {
            "projects": [
                {
                    "name": project.name,
                    "keywords": project.keywords,
                    "folder": project.folder,
                    "enable_subfolders": project.enable_subfolders,
                    **(
                        {
                            "subfolders": [
                                {
                                    "name": subfolder.name,
                                    **({"keywords": subfolder.keywords} if subfolder.keywords else {}),
                                    **({"extensions": subfolder.extensions} if subfolder.extensions else {}),
                                }
                                for subfolder in project.subfolders
                            ]
                        }
                        if project.subfolders
                        else {}
                    ),
                }
                for project in ruleset.projects
            ],
            "file_types": ruleset.file_types,
            "special_categories": {
                category.folder: {
                    **({"keywords": category.keywords} if category.keywords else {}),
                    **({"extensions": category.extensions} if category.extensions else {}),
                    **({"pattern": category.pattern} if category.pattern else {}),
                    "enable_subfolders": category.enable_subfolders,
                    **(
                        {
                            "subfolders": [
                                {
                                    "name": subfolder.name,
                                    **({"keywords": subfolder.keywords} if subfolder.keywords else {}),
                                    **({"extensions": subfolder.extensions} if subfolder.extensions else {}),
                                }
                                for subfolder in category.subfolders
                            ]
                        }
                        if category.subfolders
                        else {}
                    ),
                }
                for category in ruleset.special_categories
            },
            "misc_folder": ruleset.misc_folder,
            "other_subfolder": ruleset.other_subfolder,
        }
