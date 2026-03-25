from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - fallback for non-Qt test environments
    QApplication = None

from services.scanner import ScannerService


@unittest.skipUnless(QApplication is not None, "PyQt6 is not installed in the active interpreter")
class QtMainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from gui_qt.qt_main_window import FileOrganizerMainWindow

        cls.app = QApplication.instance() or QApplication([])
        cls.window_cls = FileOrganizerMainWindow

    def test_process_duplicates_uses_busy_callback(self) -> None:
        window = self.window_cls()
        scanner = ScannerService()

        with tempfile.TemporaryDirectory() as source_dir:
            root = Path(source_dir)
            sample = root / "2025-07" / "sample.txt"
            sample.parent.mkdir(parents=True, exist_ok=True)
            sample.write_text("same", encoding="utf-8")

            window.source_edit.setText(str(root))
            window.scanned_files = scanner.scan(root)

            with patch("gui_qt.qt_main_window.run_in_background") as mocked_runner:
                window.process_duplicates(auto_triggered=True, move_files=False)

            self.assertTrue(mocked_runner.called)
            kwargs = mocked_runner.call_args.kwargs
            self.assertIn("busy_callback", kwargs)
            self.assertTrue(callable(kwargs["busy_callback"]))

            kwargs["busy_callback"](True)
            self.assertTrue(window._busy)
            self.assertTrue(all(not button.isEnabled() for button in window.action_buttons))

            kwargs["busy_callback"](False)
            self.assertFalse(window._busy)
            self.assertTrue(all(button.isEnabled() for button in window.action_buttons))

        window.close()


if __name__ == "__main__":
    unittest.main()
