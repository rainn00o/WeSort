from __future__ import annotations

import re

from models import (
    PlanItem,
    PlanSummary,
    ProjectRule,
    ProjectSubfolderRule,
    Ruleset,
    ScannedFile,
    SpecialCategoryRule,
    SpecialSubfolderRule,
)


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", name).strip()
    return cleaned or "未命名文件"


class PlannerService:
    def build_plan(
        self,
        files: list[ScannedFile],
        ruleset: Ruleset,
        add_month_prefix: bool,
    ) -> PlanSummary:
        items = [
            self._build_item(file_info=file_info, ruleset=ruleset, add_month_prefix=add_month_prefix)
            for file_info in files
        ]
        return PlanSummary(items=items)

    def _build_item(self, file_info: ScannedFile, ruleset: Ruleset, add_month_prefix: bool) -> PlanItem:
        file_type_folder = self._resolve_file_type(file_info.extension, ruleset)
        project, project_subfolder = self._match_project(file_info, ruleset.projects, file_type_folder)

        target_name = file_info.name
        if add_month_prefix and file_info.month_tag and not target_name.startswith(f"{file_info.month_tag}_"):
            target_name = f"{file_info.month_tag}_{target_name}"
        target_name = _sanitize_filename(target_name)

        if project:
            return PlanItem(
                source=file_info,
                top_folder=project.folder,
                sub_folder=project_subfolder,
                target_name=target_name,
                category_source="project",
                matched_rule=project.name,
                confidence=self._project_confidence(file_info, project),
                reason=f"命中项目关键词：{project.name}",
            )

        special, special_subfolder = self._match_special(file_info, ruleset, file_type_folder)
        if special:
            return PlanItem(
                source=file_info,
                top_folder=special.folder,
                sub_folder=special_subfolder,
                target_name=target_name,
                category_source="special",
                matched_rule=special.folder,
                confidence=0.78,
                reason=f"命中特殊分类：{special.folder}",
            )

        return PlanItem(
            source=file_info,
            top_folder=ruleset.misc_folder,
            sub_folder=file_type_folder,
            target_name=target_name,
            category_source="misc",
            matched_rule=ruleset.misc_folder,
            confidence=0.5,
            reason="未命中项目和特殊分类，归入零散文件",
        )

    def _match_project(
        self,
        file_info: ScannedFile,
        projects: list[ProjectRule],
        fallback_subfolder: str,
    ) -> tuple[ProjectRule | None, str]:
        haystack = f"{file_info.relative_path} {file_info.name}".lower()
        scored: list[tuple[int, int, ProjectRule]] = []
        for project in projects:
            matched = [keyword for keyword in project.keywords if keyword.lower() in haystack]
            if matched:
                scored.append((len(matched), max(len(keyword) for keyword in matched), project))
        if not scored:
            return None, ""
        scored.sort(key=lambda item: (item[0], item[1], item[2].folder), reverse=True)
        project = scored[0][2]
        if not (project.enable_subfolders or bool(project.subfolders)):
            return project, ""
        subfolder = self._match_rule_subfolder(file_info, haystack, project.subfolders, fallback_subfolder)
        return project, subfolder

    def _project_confidence(self, file_info: ScannedFile, project: ProjectRule) -> float:
        haystack = f"{file_info.relative_path} {file_info.name}".lower()
        hits = sum(1 for keyword in project.keywords if keyword.lower() in haystack)
        return min(0.98, 0.68 + hits * 0.12)

    def _match_special(
        self,
        file_info: ScannedFile,
        ruleset: Ruleset,
        fallback_subfolder: str,
    ) -> tuple[SpecialCategoryRule | None, str]:
        haystack = f"{file_info.relative_path} {file_info.name}".lower()
        for category in ruleset.special_categories:
            matched = False
            if category.pattern and re.search(category.pattern, file_info.name):
                matched = True
            if not matched and file_info.extension in category.extensions:
                matched = True
            if not matched and any(keyword.lower() in haystack for keyword in category.keywords):
                matched = True
            if not matched:
                continue
            if not (category.enable_subfolders or bool(category.subfolders)):
                return category, ""
            return category, self._match_rule_subfolder(file_info, haystack, category.subfolders, fallback_subfolder)
        return None, ""

    def _match_rule_subfolder(
        self,
        file_info: ScannedFile,
        haystack: str,
        subfolders: list[ProjectSubfolderRule] | list[SpecialSubfolderRule],
        fallback_subfolder: str,
    ) -> str:
        for subfolder in subfolders:
            if any(keyword.lower() in haystack for keyword in subfolder.keywords):
                return subfolder.name
            if file_info.extension in subfolder.extensions:
                return subfolder.name
        return fallback_subfolder

    def _resolve_file_type(self, extension: str, ruleset: Ruleset) -> str:
        ext = extension.lower().strip(".")
        for folder, extensions in ruleset.file_types.items():
            if ext in extensions:
                return folder
        return ruleset.other_subfolder
