"""PyQt6 Preview dialog for WeSort."""

from __future__ import annotations

from collections import defaultdict

from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QLabel,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from models import PlanSummary


class PreviewDialog(QDialog):
    """Preview dialog using PyQt6."""

    def __init__(self, parent=None, plan: PlanSummary | None = None):
        super().__init__(parent)
        self.setWindowTitle("分类预览")
        self.resize(1000, 650)
        self.setMinimumSize(900, 550)

        if plan is None:
            plan = PlanSummary(items=[])
        self.plan = plan

        self.grouped: dict[tuple[str, str], list] = defaultdict(list)
        for item in plan.items:
            self.grouped[(item.top_folder, item.sub_folder)].append(item)

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - directory tree
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("目录结构预览")
        left_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        left_layout.addWidget(left_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemSelectionChanged.connect(self._on_select)
        left_layout.addWidget(self.tree)

        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Right side - file details
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.detail_label = QLabel("详细文件列表")
        self.detail_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        right_layout.addWidget(self.detail_label)

        self.detail = QTreeWidget()
        self.detail.setHeaderLabels([
            "原文件名", "归档文件名", "分类来源", "置信度", "命中规则", "月份标签", "原路径"
        ])
        self.detail.setColumnWidth(0, 180)
        self.detail.setColumnWidth(1, 220)
        self.detail.setColumnWidth(2, 90)
        self.detail.setColumnWidth(3, 80)
        self.detail.setColumnWidth(4, 180)
        self.detail.setColumnWidth(5, 90)
        self.detail.setColumnWidth(6, 380)
        self.detail.setAlternatingRowColors(True)
        right_layout.addWidget(self.detail)

        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)
        self.setLayout(layout)

    def _populate_tree(self):
        """Populate the directory tree."""
        folders: dict[str, QTreeWidgetItem] = {}
        for (top_folder, sub_folder), items in sorted(self.grouped.items()):
            if top_folder not in folders:
                total = sum(len(v) for k, v in self.grouped.items() if k[0] == top_folder)
                item = QTreeWidgetItem()
                item.setText(0, f"{top_folder} ({total})")
                folders[top_folder] = item
                self.tree.addTopLevelItem(item)

            if sub_folder:
                sub_item = QTreeWidgetItem()
                sub_item.setText(0, f"{sub_folder} ({len(items)})")
                sub_item.setData(0, Qt.ItemDataRole.UserRole, (top_folder, sub_folder))
                folders[top_folder].addChild(sub_item)

        if folders:
            first = next(iter(folders.values()))
            first.setSelected(True)
            self._show_top_folder(next(iter(folders.keys())))

    def _on_select(self):
        """Handle tree selection changes."""
        selected = self.tree.selectedItems()
        if not selected:
            return

        item = selected[0]
        parent = item.parent()
        text = item.text(0)
        folder_name = text.rsplit(" (", 1)[0]

        if parent:
            top_name = parent.text(0).rsplit(" (", 1)[0]
            self._show_group(top_name, folder_name)
        else:
            self._show_top_folder(folder_name)

    def _show_top_folder(self, top_folder: str):
        """Show all files in a top folder."""
        self.detail.clear()
        items = [item for item in self.plan.items if item.top_folder == top_folder]
        self.detail_label.setText(f"详细文件列表：{top_folder}")

        for item in items:
            tree_item = QTreeWidgetItem()
            tree_item.setText(0, item.source.name)
            tree_item.setText(1, item.target_name)
            tree_item.setText(2, self._describe_category_source(item.category_source))
            tree_item.setText(3, f"{item.confidence:.2f}")
            tree_item.setText(4, item.matched_rule)
            tree_item.setText(5, item.source.month_tag or "-")
            tree_item.setText(6, item.source.relative_path)
            self.detail.addTopLevelItem(tree_item)

    def _show_group(self, top_folder: str, sub_folder: str):
        """Show files in a specific subfolder."""
        self.detail.clear()
        self.detail_label.setText(f"详细文件列表：{top_folder} / {sub_folder}")

        for item in self.grouped.get((top_folder, sub_folder), []):
            tree_item = QTreeWidgetItem()
            tree_item.setText(0, item.source.name)
            tree_item.setText(1, item.target_name)
            tree_item.setText(2, self._describe_category_source(item.category_source))
            tree_item.setText(3, f"{item.confidence:.2f}")
            tree_item.setText(4, item.matched_rule)
            tree_item.setText(5, item.source.month_tag or "-")
            tree_item.setText(6, item.source.relative_path)
            self.detail.addTopLevelItem(tree_item)

    def _describe_category_source(self, category_source: str) -> str:
        """Get display name for category source."""
        mapping = {
            "project": "项目分类",
            "special": "特殊分类",
            "misc": "零散文件",
        }
        return mapping.get(category_source, category_source)
