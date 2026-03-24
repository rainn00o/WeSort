from __future__ import annotations

import csv
import hashlib
import shutil
from collections.abc import Callable
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from models import (
    DuplicateGroup,
    DuplicateScanResult,
    DuplicateTrashEntry,
    DuplicateTrashResult,
)


def _file_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_unique_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


class DuplicateService:
    def scan_duplicates(
        self,
        files: list[Path],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> DuplicateScanResult:
        size_buckets: dict[int, list[Path]] = defaultdict(list)
        total_files = len(files)
        for index, path in enumerate(files, start=1):
            size_buckets[path.stat().st_size].append(path)
            if progress_callback is not None:
                progress_callback(index, total_files, f"正在按文件大小分组 {index}/{total_files}")

        hash_candidates = [path for paths in size_buckets.values() if len(paths) > 1 for path in paths]
        total_hash_candidates = len(hash_candidates)
        buckets: dict[tuple[int, str], list[Path]] = defaultdict(list)
        for index, path in enumerate(hash_candidates, start=1):
            buckets[(path.stat().st_size, _file_hash(path))].append(path)
            if progress_callback is not None:
                progress_callback(index, total_hash_candidates, f"正在计算重复文件哈希 {index}/{total_hash_candidates}")
        groups = []
        for (size, fingerprint), paths in buckets.items():
            if len(paths) < 2:
                continue
            ordered = sorted(paths, key=lambda item: (len(str(item)), str(item)))
            groups.append(
                DuplicateGroup(
                    fingerprint=fingerprint,
                    keeper=ordered[0],
                    duplicates=ordered[1:],
                )
            )
        if progress_callback is not None and total_files == 0:
            progress_callback(0, 0, "没有可检测的文件")
        return DuplicateScanResult(groups=groups, total_files=len(files))

    def move_duplicates_to_trash(
        self,
        duplicate_result: DuplicateScanResult,
        target_dir: Path,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> DuplicateTrashResult:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        trash_dir = target_dir / "_垃圾箱_重复文件" / timestamp
        trash_dir.mkdir(parents=True, exist_ok=True)
        csv_path = trash_dir / "重复文件清单.csv"
        entries: list[DuplicateTrashEntry] = []
        moved_count = 0
        failed_count = 0
        total_duplicates = sum(len(group.duplicates) for group in duplicate_result.groups)
        processed = 0
        for group in duplicate_result.groups:
            for duplicate in group.duplicates:
                target_path = _resolve_unique_path(trash_dir, duplicate.name)
                try:
                    shutil.move(str(duplicate), str(target_path))
                    entries.append(
                        DuplicateTrashEntry(
                            source_path=str(duplicate),
                            trash_path=str(target_path),
                            status="moved",
                        )
                    )
                    moved_count += 1
                except Exception as exc:
                    entries.append(
                        DuplicateTrashEntry(
                            source_path=str(duplicate),
                            trash_path=str(target_path),
                            status="failed",
                            note=str(exc),
                        )
                    )
                    failed_count += 1
                processed += 1
                if progress_callback is not None:
                    progress_callback(processed, total_duplicates, f"正在移动重复文件 {processed}/{total_duplicates}")
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source_path", "trash_path", "status", "note"])
            for entry in entries:
                writer.writerow([entry.source_path, entry.trash_path, entry.status, entry.note])
        return DuplicateTrashResult(
            trash_dir=trash_dir,
            csv_path=csv_path,
            moved_count=moved_count,
            failed_count=failed_count,
            entries=entries,
        )
