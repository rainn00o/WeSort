from __future__ import annotations

import tkinter as tk
from collections import defaultdict
from tkinter import ttk

from models import PlanSummary


class PreviewWindow(tk.Toplevel):
    def __init__(self, master: tk.Misc, plan: PlanSummary) -> None:
        super().__init__(master)
        self.title("分类预览")
        self.geometry("1200x760")
        self.plan = plan
        self.grouped: dict[tuple[str, str], list] = defaultdict(list)
        for item in plan.items:
            self.grouped[(item.top_folder, item.sub_folder)].append(item)
        self._build_ui()
        self._populate_tree()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        paned = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        left = ttk.Frame(paned, padding=12)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="目录结构预览").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.tree = ttk.Treeview(left, show="tree")
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(left, weight=1)

        right = ttk.Frame(paned, padding=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        self.detail_label = ttk.Label(right, text="详细文件列表")
        self.detail_label.grid(row=0, column=0, sticky="w", pady=(0, 8))
        columns = ("source_name", "target_name", "source_type", "confidence", "rule", "month_tag", "source_path")
        self.detail = ttk.Treeview(right, columns=columns, show="headings")
        headings = {
            "source_name": "原文件名",
            "target_name": "归档文件名",
            "source_type": "分类来源",
            "confidence": "置信度",
            "rule": "命中规则",
            "month_tag": "月份标签",
            "source_path": "原路径",
        }
        widths = {
            "source_name": 180,
            "target_name": 220,
            "source_type": 90,
            "confidence": 80,
            "rule": 180,
            "month_tag": 90,
            "source_path": 380,
        }
        for column in columns:
            self.detail.heading(column, text=headings[column])
            self.detail.column(column, width=widths[column], anchor=tk.W)
        self.detail.grid(row=1, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.detail.yview)
        y_scroll.grid(row=1, column=1, sticky="ns")
        self.detail.configure(yscrollcommand=y_scroll.set)
        paned.add(right, weight=3)

    def _populate_tree(self) -> None:
        folders: dict[str, str] = {}
        for (top_folder, sub_folder), items in sorted(self.grouped.items()):
            if top_folder not in folders:
                folders[top_folder] = self.tree.insert("", tk.END, text=f"{top_folder} ({sum(len(v) for k, v in self.grouped.items() if k[0] == top_folder)})")
            self.tree.insert(folders[top_folder], tk.END, text=f"{sub_folder} ({len(items)})", values=(top_folder, sub_folder))
        if folders:
            first = next(iter(folders.values()))
            self.tree.selection_set(first)
            self._show_top_folder(next(iter(folders)))

    def _on_select(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        parent = self.tree.parent(item_id)
        text = self.tree.item(item_id, "text")
        folder_name = text.rsplit(" (", 1)[0]
        if parent:
            top_name = self.tree.item(parent, "text").rsplit(" (", 1)[0]
            self._show_group(top_name, folder_name)
        else:
            self._show_top_folder(folder_name)

    def _show_top_folder(self, top_folder: str) -> None:
        self.detail.delete(*self.detail.get_children())
        items = [item for item in self.plan.items if item.top_folder == top_folder]
        self.detail_label.config(text=f"详细文件列表：{top_folder}")
        for item in items:
            self.detail.insert(
                "",
                tk.END,
                values=(
                    item.source.name,
                    item.target_name,
                    self._describe_category_source(item.category_source),
                    f"{item.confidence:.2f}",
                    item.matched_rule,
                    item.source.month_tag or "-",
                    item.source.relative_path,
                ),
            )

    def _show_group(self, top_folder: str, sub_folder: str) -> None:
        self.detail.delete(*self.detail.get_children())
        self.detail_label.config(text=f"详细文件列表：{top_folder} / {sub_folder}")
        for item in self.grouped.get((top_folder, sub_folder), []):
            self.detail.insert(
                "",
                tk.END,
                values=(
                    item.source.name,
                    item.target_name,
                    self._describe_category_source(item.category_source),
                    f"{item.confidence:.2f}",
                    item.matched_rule,
                    item.source.month_tag or "-",
                    item.source.relative_path,
                ),
            )

    def _describe_category_source(self, category_source: str) -> str:
        mapping = {
            "project": "项目分类",
            "special": "特殊分类",
            "misc": "零散文件",
        }
        return mapping.get(category_source, category_source)
