from __future__ import annotations

import sys
from pathlib import Path


def run() -> None:
    """Launch the WeSort Qt application."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        raise RuntimeError(
            "当前分支仅支持 PyQt6 界面，请先安装依赖：pip install -r requirements.txt。"
        ) from exc

    from gui_qt.qt_main_window import FileOrganizerMainWindow

    app = QApplication(sys.argv)
    style_path = Path(__file__).resolve().parent / "gui" / "styles" / "modern_theme.qss"
    if style_path.exists():
        app.setStyleSheet(style_path.read_text(encoding="utf-8"))

    window = FileOrganizerMainWindow()
    window.show()
    sys.exit(app.exec())
