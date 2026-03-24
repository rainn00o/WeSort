from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.duplicates import DuplicateService


class DuplicateServiceTests(unittest.TestCase):
    def test_move_duplicates_keeps_original_names(self) -> None:
        service = DuplicateService()
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as target_dir:
            root = Path(source_dir)
            first = root / "a" / "20200326测算指标.xlsx"
            second = root / "b" / "20200326测算指标.xlsx"
            first.parent.mkdir(parents=True, exist_ok=True)
            second.parent.mkdir(parents=True, exist_ok=True)
            first.write_text("same", encoding="utf-8")
            second.write_text("same", encoding="utf-8")

            scan_result = service.scan_duplicates([first, second])
            trash_result = service.move_duplicates_to_trash(scan_result, Path(target_dir))

            self.assertEqual(trash_result.moved_count, 1)
            moved_name = Path(trash_result.entries[0].trash_path).name
            self.assertEqual(moved_name, "20200326测算指标.xlsx")
            with trash_result.csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["source_path", "trash_path", "status", "note"])

    def test_scan_duplicates_hashes_only_same_size_candidates(self) -> None:
        service = DuplicateService()
        with tempfile.TemporaryDirectory() as source_dir:
            root = Path(source_dir)
            same_one = root / "same_a.txt"
            same_two = root / "same_b.txt"
            different = root / "different.txt"
            same_one.write_text("same", encoding="utf-8")
            same_two.write_text("same", encoding="utf-8")
            different.write_text("longer-content", encoding="utf-8")

            hashed_paths: list[str] = []

            def fake_hash(path: Path, chunk_size: int = 1024 * 1024) -> str:
                hashed_paths.append(path.name)
                return "same-hash"

            with patch("services.duplicates._file_hash", side_effect=fake_hash):
                result = service.scan_duplicates([same_one, same_two, different])

            self.assertEqual(sorted(hashed_paths), ["same_a.txt", "same_b.txt"])
            self.assertEqual(result.duplicate_count, 1)


if __name__ == "__main__":
    unittest.main()
