from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class ScannedFile:
    source_path: Path
    relative_path: str
    name: str
    stem: str
    extension: str
    size: int
    modified_at: datetime
    month_tag: str = ""


@dataclass(slots=True)
class ProjectSubfolderRule:
    name: str
    keywords: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ProjectRule:
    name: str
    keywords: list[str]
    folder: str
    enable_subfolders: bool = False
    subfolders: list[ProjectSubfolderRule] = field(default_factory=list)


@dataclass(slots=True)
class SpecialSubfolderRule:
    name: str
    keywords: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SpecialCategoryRule:
    folder: str
    keywords: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=list)
    pattern: str = ""
    enable_subfolders: bool = False
    subfolders: list[SpecialSubfolderRule] = field(default_factory=list)


@dataclass(slots=True)
class Ruleset:
    projects: list[ProjectRule]
    file_types: dict[str, list[str]]
    special_categories: list[SpecialCategoryRule]
    misc_folder: str = "90_零散文件"
    other_subfolder: str = "其他文件"


@dataclass(slots=True)
class DuplicateGroup:
    fingerprint: str
    keeper: Path
    duplicates: list[Path]


@dataclass(slots=True)
class DuplicateScanResult:
    groups: list[DuplicateGroup]
    total_files: int

    @property
    def duplicate_count(self) -> int:
        return sum(len(group.duplicates) for group in self.groups)


@dataclass(slots=True)
class DuplicateTrashEntry:
    source_path: str
    trash_path: str
    status: str
    note: str = ""


@dataclass(slots=True)
class DuplicateTrashResult:
    trash_dir: Path
    csv_path: Path
    moved_count: int
    failed_count: int
    entries: list[DuplicateTrashEntry]


@dataclass(slots=True)
class PlanItem:
    source: ScannedFile
    top_folder: str
    sub_folder: str
    target_name: str
    category_source: str
    matched_rule: str
    confidence: float
    reason: str

    @property
    def target_relative_path(self) -> Path:
        if self.sub_folder:
            return Path(self.top_folder) / self.sub_folder / self.target_name
        return Path(self.top_folder) / self.target_name


@dataclass(slots=True)
class PlanSummary:
    items: list[PlanItem]

    @property
    def total_files(self) -> int:
        return len(self.items)

    @property
    def top_folders(self) -> list[str]:
        return sorted({item.top_folder for item in self.items})


@dataclass(slots=True)
class ExecutionEntry:
    source_path: str
    target_path: str
    status: str
    note: str = ""


@dataclass(slots=True)
class ExecutionResult:
    output_root: Path
    moved_count: int
    failed_count: int
    report_json: Path | None
    report_txt: Path | None
    entries: list[ExecutionEntry]
