from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.scanner import ScannerService


class ScannerServiceTests(unittest.TestCase):
    def test_scan_reports_progress(self) -> None:
        service = ScannerService()
        with tempfile.TemporaryDirectory() as source_dir:
            root = Path(source_dir)
            (root / "a.txt").write_text("a", encoding="utf-8")
            nested = root / "nested"
            nested.mkdir()
            (nested / "b.txt").write_text("b", encoding="utf-8")

            progress_calls: list[tuple[int, int, str]] = []
            files = service.scan(
                root,
                progress_callback=lambda current, total, message: progress_calls.append((current, total, message)),
            )

            self.assertEqual(len(files), 2)
            self.assertTrue(progress_calls)
            self.assertEqual(progress_calls[-1][0], 2)
            self.assertEqual(progress_calls[-1][1], 2)


if __name__ == "__main__":
    unittest.main()
