from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from models import ScannedFile
from services.months import resolve_month_tag


class ScannerService:
    def scan(
        self,
        source_dir: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[ScannedFile]:
        root = source_dir.resolve()
        all_files = [path for path in sorted(root.rglob("*")) if path.is_file()]
        total_files = len(all_files)
        scanned_files: list[ScannedFile] = []
        for index, path in enumerate(all_files, start=1):
            stat = path.stat()
            scanned_files.append(
                ScannedFile(
                    source_path=path,
                    relative_path=str(path.relative_to(root)),
                    name=path.name,
                    stem=path.stem,
                    extension=path.suffix.lower().strip("."),
                    size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime),
                    month_tag=resolve_month_tag(path, root),
                )
            )
            if progress_callback is not None:
                progress_callback(index, total_files, f"正在扫描文件 {index}/{total_files}")
        return scanned_files
