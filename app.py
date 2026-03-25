from __future__ import annotations

import os
import sys
from pathlib import Path


def run() -> None:
    """Launch the WeSort application."""
    use_qt = os.environ.get("WESORT_GUI", "qt").lower() == "qt"
    if use_qt:
        _run_qt()
        return
    _run_tkinter()


def _run_qt() -> None:
    """Launch the PyQt6 application."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "当前分支默认使用 PyQt6 界面，请先安装依赖：pip install -r requirements.txt，"
            "或设置环境变量 WESORT_GUI=tk 使用 Tk 版本。"
        ) from exc

    from gui_qt.qt_main_window import FileOrganizerMainWindow

    app = QApplication(sys.argv)
    style_path = Path(__file__).resolve().parent / "gui" / "styles" / "modern_theme.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = FileOrganizerMainWindow()
    window.show()
    sys.exit(app.exec())


def _run_tkinter() -> None:
    """Launch the Tkinter application."""
    from gui.main_window import FileOrganizerGUI

    FileOrganizerGUI().run()
