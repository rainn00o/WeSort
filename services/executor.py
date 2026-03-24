from __future__ import annotations

import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from models import ExecutionEntry, ExecutionResult, PlanSummary


def _resolve_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


class ExecutorService:
    def execute(
        self,
        plan: PlanSummary,
        output_root: Path,
        generate_report: bool,
    ) -> ExecutionResult:
        output_root.mkdir(parents=True, exist_ok=True)
        entries: list[ExecutionEntry] = []
        moved_count = 0
        failed_count = 0
        for item in plan.items:
            destination = output_root / item.target_relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = _resolve_unique_path(destination)
            try:
                shutil.move(str(item.source.source_path), str(destination))
                entries.append(
                    ExecutionEntry(
                        source_path=str(item.source.source_path),
                        target_path=str(destination),
                        status="moved",
                    )
                )
                moved_count += 1
            except Exception as exc:
                entries.append(
                    ExecutionEntry(
                        source_path=str(item.source.source_path),
                        target_path=str(destination),
                        status="failed",
                        note=str(exc),
                    )
                )
                failed_count += 1
        report_txt: Path | None = None
        if generate_report:
            report_txt = self._write_report(output_root, plan, entries)
        return ExecutionResult(
            output_root=output_root,
            moved_count=moved_count,
            failed_count=failed_count,
            report_json=None,
            report_txt=report_txt,
            entries=entries,
        )

    def _write_report(
        self,
        output_root: Path,
        plan: PlanSummary,
        entries: list[ExecutionEntry],
    ) -> Path:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        report_txt = output_root / f"classification_report_{timestamp}.txt"
        grouped = defaultdict(int)
        for item in plan.items:
            folder_key = item.top_folder if not item.sub_folder else f"{item.top_folder}/{item.sub_folder}"
            grouped[folder_key] += 1
        lines = [
            f"生成时间：{timestamp}",
            f"总文件数：{len(entries)}",
            f"成功移动：{sum(1 for entry in entries if entry.status == 'moved')}",
            f"失败数量：{sum(1 for entry in entries if entry.status != 'moved')}",
            "",
            "目录统计：",
        ]
        lines.extend(f"- {folder}: {count}" for folder, count in sorted(grouped.items()))
        report_txt.write_text("\n".join(lines), encoding="utf-8")
        return report_txt
