from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import run


def main() -> None:
    try:
        run()
    except Exception as exc:
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("启动错误", f"程序启动失败: {exc}")
            root.destroy()
        except Exception:
            print(f"程序启动失败: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
