from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

from gui.main_window import FileOrganizerGUI
from models import ScannedFile


class MainWindowHelperTests(unittest.TestCase):
    def test_month_display_falls_back_to_relative_path(self) -> None:
        app = FileOrganizerGUI()
        try:
            scanned = ScannedFile(
                source_path=Path("J:/tmp/demo.pdf"),
                relative_path="wechat/2025-07/demo.pdf",
                name="demo.pdf",
                stem="demo",
                extension="pdf",
                size=1024,
                modified_at=datetime.now(),
                month_tag="",
            )
            self.assertEqual(app._resolve_scan_month_display(scanned), "2025-07")
        finally:
            app.root.destroy()

    def test_size_is_formatted_in_mb(self) -> None:
        app = FileOrganizerGUI()
        try:
            self.assertEqual(app._format_size_mb(1048576), "1.00")
            self.assertEqual(app._format_size_mb(15 * 1024 * 1024), "15.0")
        finally:
            app.root.destroy()

    def test_sort_scan_table_by_size_toggles_direction(self) -> None:
        app = FileOrganizerGUI()
        try:
            app.scanned_files = [
                ScannedFile(
                    source_path=Path("J:/tmp/b.pdf"),
                    relative_path="2025-07/b.pdf",
                    name="b.pdf",
                    stem="b",
                    extension="pdf",
                    size=10,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
                ScannedFile(
                    source_path=Path("J:/tmp/a.pdf"),
                    relative_path="2025-07/a.pdf",
                    name="a.pdf",
                    stem="a",
                    extension="pdf",
                    size=20,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
            ]
            app._sort_scan_table("size")
            self.assertEqual([item.size for item in app.scanned_files], [10, 20])
            app._sort_scan_table("size")
            self.assertEqual([item.size for item in app.scanned_files], [20, 10])
        finally:
            app.root.destroy()

    def test_sort_scan_table_by_name(self) -> None:
        app = FileOrganizerGUI()
        try:
            app.scanned_files = [
                ScannedFile(
                    source_path=Path("J:/tmp/b.pdf"),
                    relative_path="2025-07/b.pdf",
                    name="b.pdf",
                    stem="b",
                    extension="pdf",
                    size=10,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
                ScannedFile(
                    source_path=Path("J:/tmp/a.pdf"),
                    relative_path="2025-07/a.pdf",
                    name="a.pdf",
                    stem="a",
                    extension="pdf",
                    size=20,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
            ]
            app._sort_scan_table("name")
            self.assertEqual([item.name for item in app.scanned_files], ["a.pdf", "b.pdf"])
        finally:
            app.root.destroy()

    def test_sort_scan_table_by_month_puts_unknown_last(self) -> None:
        app = FileOrganizerGUI()
        try:
            app.scanned_files = [
                ScannedFile(
                    source_path=Path("J:/tmp/no-month.pdf"),
                    relative_path="misc/no-month.pdf",
                    name="no-month.pdf",
                    stem="no-month",
                    extension="pdf",
                    size=10,
                    modified_at=datetime.now(),
                    month_tag="",
                ),
                ScannedFile(
                    source_path=Path("J:/tmp/month.pdf"),
                    relative_path="2025-07/month.pdf",
                    name="month.pdf",
                    stem="month",
                    extension="pdf",
                    size=20,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
            ]
            app._sort_scan_table("month_tag")
            self.assertEqual(
                [app._resolve_scan_month_display(item) for item in app.scanned_files],
                ["2025-07", "-"],
            )
        finally:
            app.root.destroy()

    def test_sort_scan_table_by_extension(self) -> None:
        app = FileOrganizerGUI()
        try:
            app.scanned_files = [
                ScannedFile(
                    source_path=Path("J:/tmp/a.skp"),
                    relative_path="2025-07/a.skp",
                    name="a.skp",
                    stem="a",
                    extension="skp",
                    size=10,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
                ScannedFile(
                    source_path=Path("J:/tmp/b.pdf"),
                    relative_path="2025-07/b.pdf",
                    name="b.pdf",
                    stem="b",
                    extension="pdf",
                    size=20,
                    modified_at=datetime.now(),
                    month_tag="2025-07",
                ),
            ]
            app._sort_scan_table("extension")
            self.assertEqual([item.extension for item in app.scanned_files], ["pdf", "skp"])
        finally:
            app.root.destroy()


if __name__ == "__main__":
    unittest.main()
