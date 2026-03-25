"""PyQt6 Rule Editor dialog for WeSort."""

from __future__ import annotations

import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from models import (
    PlanItem,
    ProjectRule,
    ProjectSubfolderRule,
    Ruleset,
    ScannedFile,
    SpecialCategoryRule,
    SpecialSubfolderRule,
)
from services.ai_rules import AIRulesError, AIRulesService
from services.planner import PlannerService


PRESET_AI_PROMPTS = {
    "生成初版规则": "请基于当前文件样本，优先识别明确项目，再补充特殊分类，最后保留零散文件兜底，生成一版清晰可执行的分类规则。",
    "合并相近项目": "请检查当前项目规则中是否存在名称不同但内容接近的项目，如果有，请合并相近项目并保留更清晰的项目名称。",
    "拆分过大项目": "请检查是否有项目范围过大、关键词过宽的情况；如果存在，请拆分成更清晰的多个项目分类。",
    "强化特殊分类": "请补充和优化特殊分类，重点识别设计素材、软件工具字体、AI新闻资讯、规范标准文档等补充目录。",
    "收紧零散文件": "请尽量把可明确识别的文件归入项目或特殊分类，只把无法稳定判断的文件保留在零散文件中。",
    "统一命名结构": "请统一项目目录命名、特殊分类目录命名和关键词风格，避免重复、歧义和层级混乱。",
}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _subfolders_to_text(subfolders: list) -> str:
    lines = []
    for subfolder in subfolders:
        lines.append(f"{subfolder.name}:{','.join(subfolder.keywords)}|{','.join(subfolder.extensions)}")
    return "\n".join(lines)


def _project_subfolders_from_text(value: str) -> list:
    result = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, remainder = line.split(":", 1)
        keywords_text, _, ext_text = remainder.partition("|")
        folder_name = name.strip()
        if not folder_name:
            continue
        result.append(
            ProjectSubfolderRule(
                name=folder_name,
                keywords=_split_csv(keywords_text),
                extensions=[item.lower().strip(". ") for item in _split_csv(ext_text)],
            )
        )
    return result


def _special_subfolders_from_text(value: str) -> list:
    result = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        name, remainder = line.split(":", 1)
        keywords_text, _, ext_text = remainder.partition("|")
        folder_name = name.strip()
        if not folder_name:
            continue
        result.append(
            SpecialSubfolderRule(
                name=folder_name,
                keywords=_split_csv(keywords_text),
                extensions=[item.lower().strip(". ") for item in _split_csv(ext_text)],
            )
        )
    return result


class AIRulesThread(QThread):
    """Thread for AI rules generation."""
    finished = pyqtSignal(object)
    error = pyqtSignal(Exception)

    def __init__(self, service, scanned_paths, existing_rules, user_request, history, reset):
        super().__init__()
        self.service = service
        self.scanned_paths = scanned_paths
        self.existing_rules = existing_rules
        self.user_request = user_request
        self.history = history
        self.reset = reset

    def run(self):
        try:
            result = self.service.suggest_rules(
                scanned_paths=self.scanned_paths,
                existing_rules=self.existing_rules,
                user_request=self.user_request,
                conversation_history=self.history,
                reset_existing_results=self.reset,
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(e)


class RuleEditorDialog(QDialog):
    """Rule Editor dialog using PyQt6."""

    def __init__(
        self,
        parent=None,
        ruleset: Ruleset | None = None,
        scanned_files: list[ScannedFile] | None = None,
        add_month_prefix: bool = True,
        on_save=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("AI辅助创建分类规则")
        self.resize(1100, 800)
        self.setMinimumSize(1000, 700)

        if ruleset is None:
            ruleset = Ruleset(projects=[], special_categories=[], misc_folder="90_零散文件", other_subfolder="其他文件")
        if scanned_files is None:
            scanned_files = []

        self.ruleset = deepcopy(ruleset)
        self.scanned_files = list(scanned_files)
        self.add_month_prefix = add_month_prefix
        self.on_save = on_save or (lambda ruleset: None)

        self.ai_service = AIRulesService()
        self.planner = PlannerService()
        self.project_index: int | None = None
        self.special_index: int | None = None
        self.preview_lookup: dict[tuple[str, str], list[PlanItem]] = {}
        self.chat_history: list[tuple[str, str]] = []
        self.ai_running = False
        self.ai_thread: AIRulesThread | None = None

        self._build_ui()
        self._refresh_all()

    def _build_ui(self):
        """Build the dialog UI."""
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)

        # Use vertical splitter for adjustable sections
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Tab widget for different rule categories
        self.tab_widget = QTabWidget()

        self.project_tab = QWidget()
        self._build_project_tab()
        self.tab_widget.addTab(self.project_tab, "项目分类")

        self.special_tab = QWidget()
        self._build_special_tab()
        self.tab_widget.addTab(self.special_tab, "特殊分类")

        self.preview_tab = QWidget()
        self._build_preview_tab()
        self.tab_widget.addTab(self.preview_tab, "命中文件预览")

        splitter.addWidget(self.tab_widget)

        # AI Assistant section
        ai_group = QGroupBox("AI辅助与保存")
        ai_layout = QVBoxLayout()
        ai_layout.setContentsMargins(16, 20, 16, 16)
        ai_layout.setSpacing(8)

        # Horizontal splitter for chat and prompt areas
        ai_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Chat history
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        chat_label = QLabel("对话记录")
        chat_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        left_layout.addWidget(chat_label)

        self.chat_text = QTextEdit()
        self.chat_text.setReadOnly(True)
        self.chat_text.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                border: 2px solid #E0E6ED;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        left_layout.addWidget(self.chat_text)

        left_widget.setLayout(left_layout)
        ai_splitter.addWidget(left_widget)

        # Right side - Prompt input
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        prompt_label = QLabel("补充要求")
        prompt_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        right_layout.addWidget(prompt_label)

        prompt_row = QWidget()
        prompt_row_layout = QHBoxLayout()
        prompt_row_layout.setContentsMargins(0, 0, 0, 0)

        self.preset_prompt_combo = QComboBox()
        self.preset_prompt_combo.addItems(list(PRESET_AI_PROMPTS.keys()))
        prompt_row_layout.addWidget(self.preset_prompt_combo, stretch=1)

        insert_preset_button = QPushButton("插入预设提示词")
        insert_preset_button.clicked.connect(self._insert_preset_prompt)
        prompt_row_layout.addWidget(insert_preset_button)

        prompt_row.setLayout(prompt_row_layout)
        right_layout.addWidget(prompt_row)

        self.ai_prompt = QTextEdit()
        self.ai_prompt.setStyleSheet("""
            QTextEdit {
                background-color: #FFFFFF;
                border: 2px solid #E0E6ED;
                border-radius: 8px;
                padding: 8px;
            }
        """)
        right_layout.addWidget(self.ai_prompt)

        right_widget.setLayout(right_layout)
        ai_splitter.addWidget(right_widget)

        # Set horizontal splitter sizes: 50% each
        ai_splitter.setStretchFactor(0, 1)
        ai_splitter.setStretchFactor(1, 1)
        ai_splitter.setSizes([400, 400])

        ai_layout.addWidget(ai_splitter)

        # Status and buttons
        self.status_label = QLabel("你可以直接编辑规则，也可以先让 AI 生成建议。")
        self.status_label.setStyleSheet("color: #666666; font-size: 12px;")
        ai_layout.addWidget(self.status_label)

        button_row = QWidget()
        button_row_layout = QHBoxLayout()
        button_row_layout.setContentsMargins(0, 0, 0, 0)

        self.ai_button = QPushButton("使用AI生成建议")
        self.ai_button.clicked.connect(self._use_ai)
        button_row_layout.addWidget(self.ai_button)

        save_rules_button = QPushButton("保存规则")
        save_rules_button.clicked.connect(self._save_rules)
        button_row_layout.addWidget(save_rules_button)

        button_row.setLayout(button_row_layout)
        ai_layout.addWidget(button_row, alignment=Qt.AlignmentFlag.AlignRight)

        ai_group.setLayout(ai_layout)
        splitter.addWidget(ai_group)

        # Set initial sizes: 60% for tabs, 40% for AI section
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([480, 320])

        layout.addWidget(splitter)
        self.setLayout(layout)

        self._append_chat("系统", "你可以先让 AI 生成一版规则，然后继续输入要求来调整当前结构。")

    def _build_project_tab(self):
        """Build the project rules tab."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - project list
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("项目列表")
        left_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        left_layout.addWidget(left_label)

        self.project_list = QListWidget()
        self.project_list.setMaximumWidth(250)
        self.project_list.itemSelectionChanged.connect(self._on_project_select)
        left_layout.addWidget(self.project_list)

        add_project_button = QPushButton("新增项目")
        add_project_button.clicked.connect(self._add_project)
        left_layout.addWidget(add_project_button)

        delete_project_button = QPushButton("删除项目")
        delete_project_button.clicked.connect(self._delete_project)
        left_layout.addWidget(delete_project_button)

        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Right - project form
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("项目名称")
        right_layout.addWidget(QLabel("项目名称:"))
        right_layout.addWidget(self.project_name_edit)

        self.project_folder_edit = QLineEdit()
        self.project_folder_edit.setPlaceholderText("目录名称")
        right_layout.addWidget(QLabel("目录名称:"))
        right_layout.addWidget(self.project_folder_edit)

        self.project_keywords_edit = QLineEdit()
        self.project_keywords_edit.setPlaceholderText("关键词（逗号分隔）")
        right_layout.addWidget(QLabel("关键词（逗号分隔）:"))
        right_layout.addWidget(self.project_keywords_edit)

        self.enable_project_subfolders_check = QCheckBox("启用项目子目录细分")
        self.enable_project_subfolders_check.stateChanged.connect(self._update_project_subfolder_editor_state)
        right_layout.addWidget(self.enable_project_subfolders_check)

        right_layout.addWidget(QLabel("项目子目录规则（每行：子目录:关键词1,关键词2|ext1,ext2）:"))
        self.project_subfolders_text = QTextEdit()
        self.project_subfolders_text.setMaximumHeight(120)
        right_layout.addWidget(self.project_subfolders_text)

        save_project_button = QPushButton("保存当前项目")
        save_project_button.clicked.connect(self._save_project)
        right_layout.addWidget(save_project_button, alignment=Qt.AlignmentFlag.AlignRight)

        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)
        self.project_tab.setLayout(layout)

    def _build_special_tab(self):
        """Build the special categories tab."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - special category list
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("特殊分类列表")
        left_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        left_layout.addWidget(left_label)

        self.special_list = QListWidget()
        self.special_list.setMaximumWidth(250)
        self.special_list.itemSelectionChanged.connect(self._on_special_select)
        left_layout.addWidget(self.special_list)

        add_special_button = QPushButton("新增特殊分类")
        add_special_button.clicked.connect(self._add_special)
        left_layout.addWidget(add_special_button)

        delete_special_button = QPushButton("删除特殊分类")
        delete_special_button.clicked.connect(self._delete_special)
        left_layout.addWidget(delete_special_button)

        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Right - special form
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.special_folder_edit = QLineEdit()
        self.special_folder_edit.setPlaceholderText("目录名称")
        right_layout.addWidget(QLabel("目录名称:"))
        right_layout.addWidget(self.special_folder_edit)

        self.special_keywords_edit = QLineEdit()
        self.special_keywords_edit.setPlaceholderText("关键词（逗号分隔）")
        right_layout.addWidget(QLabel("关键词（逗号分隔）:"))
        right_layout.addWidget(self.special_keywords_edit)

        self.special_extensions_edit = QLineEdit()
        self.special_extensions_edit.setPlaceholderText("扩展名（逗号分隔）")
        right_layout.addWidget(QLabel("扩展名（逗号分隔）:"))
        right_layout.addWidget(self.special_extensions_edit)

        self.special_pattern_edit = QLineEdit()
        self.special_pattern_edit.setPlaceholderText("正则表达式")
        right_layout.addWidget(QLabel("正则表达式:"))
        right_layout.addWidget(self.special_pattern_edit)

        self.enable_special_subfolders_check = QCheckBox("启用特殊分类子目录细分")
        self.enable_special_subfolders_check.stateChanged.connect(self._update_special_subfolder_editor_state)
        right_layout.addWidget(self.enable_special_subfolders_check)

        right_layout.addWidget(QLabel("特殊分类子目录规则（每行：子目录:关键词1,关键词2|ext1,ext2）:"))
        self.special_subfolders_text = QTextEdit()
        self.special_subfolders_text.setMaximumHeight(120)
        right_layout.addWidget(self.special_subfolders_text)

        save_special_button = QPushButton("保存当前特殊分类")
        save_special_button.clicked.connect(self._save_special)
        right_layout.addWidget(save_special_button, alignment=Qt.AlignmentFlag.AlignRight)

        # Misc settings
        misc_group = QGroupBox("兜底目录设置")
        misc_layout = QVBoxLayout()

        misc_folder_row = QWidget()
        misc_folder_row_layout = QVBoxLayout()
        misc_folder_row_layout.setContentsMargins(0, 0, 0, 0)
        self.misc_folder_edit = QLineEdit()
        self.misc_folder_edit.setPlaceholderText("零散文件目录")
        misc_folder_row_layout.addWidget(QLabel("零散文件目录:"))
        misc_folder_row_layout.addWidget(self.misc_folder_edit)
        misc_folder_row.setLayout(misc_folder_row_layout)
        misc_layout.addWidget(misc_folder_row)

        other_subfolder_row = QWidget()
        other_subfolder_row_layout = QVBoxLayout()
        other_subfolder_row_layout.setContentsMargins(0, 0, 0, 0)
        self.other_subfolder_edit = QLineEdit()
        self.other_subfolder_edit.setPlaceholderText("默认细分类名称")
        other_subfolder_row_layout.addWidget(QLabel("默认细分类名称:"))
        other_subfolder_row_layout.addWidget(self.other_subfolder_edit)
        other_subfolder_row.setLayout(other_subfolder_row_layout)
        misc_layout.addWidget(other_subfolder_row)

        misc_group.setLayout(misc_layout)
        right_layout.addWidget(misc_group)

        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)
        self.special_tab.setLayout(layout)

    def _build_preview_tab(self):
        """Build the preview tab."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left - preview tree
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_label = QLabel("分类计划目录树")
        left_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        left_layout.addWidget(left_label)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderHidden(True)
        self.preview_tree.itemSelectionChanged.connect(self._on_preview_select)
        left_layout.addWidget(self.preview_tree)

        left_widget.setLayout(left_layout)
        splitter.addWidget(left_widget)

        # Right - preview details
        right_widget = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_label = QLabel("分类计划详细文件")
        self.preview_label.setStyleSheet("font-weight: 600; color: #2C3E50;")
        right_layout.addWidget(self.preview_label)

        self.preview_detail = QTreeWidget()
        self.preview_detail.setHeaderLabels([
            "原文件名", "归档文件名", "月份标签", "分类来源", "置信度", "命中规则", "原路径"
        ])
        self.preview_detail.setColumnWidth(0, 180)
        self.preview_detail.setColumnWidth(1, 220)
        self.preview_detail.setColumnWidth(2, 90)
        self.preview_detail.setColumnWidth(3, 90)
        self.preview_detail.setColumnWidth(4, 80)
        self.preview_detail.setColumnWidth(5, 180)
        self.preview_detail.setColumnWidth(6, 380)
        self.preview_detail.setAlternatingRowColors(True)
        right_layout.addWidget(self.preview_detail)

        right_widget.setLayout(right_layout)
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)
        self.preview_tab.setLayout(layout)

    def _refresh_all(self):
        """Refresh all UI elements."""
        self.misc_folder_edit.setText(self.ruleset.misc_folder)
        self.other_subfolder_edit.setText(self.ruleset.other_subfolder)
        self._refresh_project_list()
        self._refresh_special_list()
        self._refresh_preview_tree()

    def _append_chat(self, role: str, message: str):
        """Append message to chat history."""
        self.chat_history.append((role, message))
        self._append_chat_view(role, message)

    def _append_chat_view(self, role: str, message: str):
        """Append message to chat view."""
        color = "#666666" if role == "系统" else "#0b3d91" if role == "你" else "#1f6f43"
        self.chat_text.append(f'<span style="color: {color};"><b>{role}:</b> {message}</span>')

    def _insert_preset_prompt(self):
        """Insert preset prompt."""
        prompt = PRESET_AI_PROMPTS.get(self.preset_prompt_combo.currentText(), "")
        if not prompt:
            return
        current = self.ai_prompt.toPlainText().strip()
        merged = prompt if not current else f"{current}\n{prompt}"
        self.ai_prompt.setPlainText(merged)

    def _refresh_project_list(self):
        """Refresh the project list."""
        self.project_list.clear()
        for project in self.ruleset.projects:
            marker = " [细分]" if (project.enable_subfolders or bool(project.subfolders)) else ""
            self.project_list.addItem(f"{project.folder} | {project.name}{marker}")

    def _refresh_special_list(self):
        """Refresh the special category list."""
        self.special_list.clear()
        self.special_list.addItem(f"零散文件目录 | {self.ruleset.misc_folder}")
        self.special_list.addItem(f"默认细分类 | {self.ruleset.other_subfolder}")
        for category in self.ruleset.special_categories:
            marker = " [细分]" if (category.enable_subfolders or bool(category.subfolders)) else ""
            self.special_list.addItem(f"{category.folder}{marker}")

    def _build_preview_cache(self):
        """Build preview lookup cache."""
        plan = self.planner.build_plan(self.scanned_files, self.ruleset, add_month_prefix=self.add_month_prefix)
        lookup: dict[tuple[str, str], list[PlanItem]] = defaultdict(list)
        for item in plan.items:
            lookup[(item.top_folder, item.sub_folder)].append(item)
        self.preview_lookup = dict(lookup)

    def _refresh_preview_tree(self):
        """Refresh the preview tree."""
        self._build_preview_cache()
        self.preview_tree.clear()

        parents: dict[str, QTreeWidgetItem] = {}
        for (top_folder, sub_folder), items in sorted(self.preview_lookup.items()):
            if top_folder not in parents:
                total = sum(len(group) for (folder, _), group in self.preview_lookup.items() if folder == top_folder)
                item = QTreeWidgetItem()
                item.setText(0, f"{top_folder} ({total})")
                parents[top_folder] = item
                self.preview_tree.addTopLevelItem(item)

            if sub_folder:
                sub_item = QTreeWidgetItem()
                sub_item.setText(0, f"{sub_folder} ({len(items)})")
                sub_item.setData(0, Qt.ItemDataRole.UserRole, (top_folder, sub_folder))
                parents[top_folder].addChild(sub_item)

        if parents:
            first_parent = next(iter(parents.values()))
            first_parent.setSelected(True)
            self._show_preview_group(next(iter(parents.keys())), "")

    def _show_preview_group(self, top_folder: str, sub_folder: str):
        """Show preview group details."""
        self.preview_detail.clear()

        if sub_folder:
            items = self.preview_lookup.get((top_folder, sub_folder), [])
            title = f"命中文件列表：{top_folder} / {sub_folder}"
        else:
            items = [
                item for (folder, _), group in self.preview_lookup.items()
                if folder == top_folder for item in group
            ]
            title = f"命中文件列表：{top_folder}"

        self.preview_label.setText(title)

        for item in items:
            tree_item = QTreeWidgetItem()
            tree_item.setText(0, item.source.name)
            tree_item.setText(1, item.target_name)
            tree_item.setText(2, item.source.month_tag or "-")
            tree_item.setText(3, self._describe_category_source(item.category_source))
            tree_item.setText(4, f"{item.confidence:.2f}")
            tree_item.setText(5, item.matched_rule)
            tree_item.setText(6, item.source.relative_path)
            self.preview_detail.addTopLevelItem(tree_item)

    def _describe_category_source(self, category_source: str) -> str:
        """Get display name for category source."""
        mapping = {
            "project": "项目分类",
            "special": "特殊分类",
            "misc": "零散文件",
        }
        return mapping.get(category_source, category_source)

    def _on_preview_select(self):
        """Handle preview tree selection."""
        selected = self.preview_tree.selectedItems()
        if not selected:
            return

        item = selected[0]
        parent = item.parent()
        label = item.text(0).rsplit(" (", 1)[0]

        if parent:
            top_folder = parent.text(0).rsplit(" (", 1)[0]
            self._show_preview_group(top_folder, label)
        else:
            self._show_preview_group(label, "")

    def _on_project_select(self):
        """Handle project selection."""
        selected = self.project_list.selectedItems()
        if not selected:
            return

        self.project_index = self.project_list.row(selected[0])
        project = self.ruleset.projects[self.project_index]

        self.project_name_edit.setText(project.name)
        self.project_folder_edit.setText(project.folder)
        self.project_keywords_edit.setText(",".join(project.keywords))
        self.enable_project_subfolders_check.setChecked(project.enable_subfolders or bool(project.subfolders))
        self.project_subfolders_text.setPlainText(_subfolders_to_text(project.subfolders))
        self._update_project_subfolder_editor_state()

    def _on_special_select(self):
        """Handle special category selection."""
        selected = self.special_list.selectedItems()
        if not selected:
            return

        index = self.special_list.row(selected[0])
        if index < 2:
            return

        self.special_index = index - 2
        category = self.ruleset.special_categories[self.special_index]

        self.special_folder_edit.setText(category.folder)
        self.special_keywords_edit.setText(",".join(category.keywords))
        self.special_extensions_edit.setText(",".join(category.extensions))
        self.special_pattern_edit.setText(category.pattern)
        self.enable_special_subfolders_check.setChecked(category.enable_subfolders or bool(category.subfolders))
        self.special_subfolders_text.setPlainText(_subfolders_to_text(category.subfolders))
        self._update_special_subfolder_editor_state()

    def _add_project(self):
        """Add a new project."""
        index = len(self.ruleset.projects) + 1
        self.ruleset.projects.append(
            ProjectRule(name=f"新项目{index}", keywords=[], folder=f"{index:02d}_新项目{index}")
        )
        self._refresh_all()
        last = self.project_list.count() - 1
        if last >= 0:
            self.project_list.setCurrentRow(last)
            self._on_project_select()

    def _delete_project(self):
        """Delete selected project."""
        if self.project_index is None:
            return
        del self.ruleset.projects[self.project_index]
        self.project_index = None
        self.project_name_edit.clear()
        self.project_folder_edit.clear()
        self.project_keywords_edit.clear()
        self.enable_project_subfolders_check.setChecked(False)
        self.project_subfolders_text.clear()
        self._update_project_subfolder_editor_state()
        self._refresh_all()

    def _save_project(self):
        """Save current project."""
        if self.project_index is None:
            QMessageBox.warning(self, "提示", "请先选择一个项目。")
            return

        name = self.project_name_edit.text().strip()
        folder = self.project_folder_edit.text().strip()
        if not name or not folder:
            QMessageBox.warning(self, "提示", "项目名称和目录名称不能为空。")
            return

        enable_subfolders = self.enable_project_subfolders_check.isChecked()
        subfolders = _project_subfolders_from_text(self.project_subfolders_text.toPlainText()) if enable_subfolders else []

        self.ruleset.projects[self.project_index] = ProjectRule(
            name=name,
            folder=folder,
            keywords=_split_csv(self.project_keywords_edit.text()),
            enable_subfolders=enable_subfolders,
            subfolders=subfolders,
        )
        self._apply_misc_settings()
        self._refresh_all()
        self.project_list.setCurrentRow(self.project_index)
        self._on_project_select()

    def _add_special(self):
        """Add a new special category."""
        self.ruleset.special_categories.append(SpecialCategoryRule(folder="98_新特殊分类"))
        self._refresh_all()
        last = self.special_list.count() - 1
        if last >= 0:
            self.special_list.setCurrentRow(last)
            self._on_special_select()

    def _delete_special(self):
        """Delete selected special category."""
        if self.special_index is None:
            return
        del self.ruleset.special_categories[self.special_index]
        self.special_index = None
        self.special_folder_edit.clear()
        self.special_keywords_edit.clear()
        self.special_extensions_edit.clear()
        self.special_pattern_edit.clear()
        self.enable_special_subfolders_check.setChecked(False)
        self.special_subfolders_text.clear()
        self._update_special_subfolder_editor_state()
        self._refresh_all()

    def _save_special(self):
        """Save current special category."""
        if self.special_index is None:
            QMessageBox.warning(self, "提示", "请先选择一个特殊分类。")
            return

        folder = self.special_folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "提示", "目录名称不能为空。")
            return

        enable_subfolders = self.enable_special_subfolders_check.isChecked()
        subfolders = _special_subfolders_from_text(self.special_subfolders_text.toPlainText()) if enable_subfolders else []

        self.ruleset.special_categories[self.special_index] = SpecialCategoryRule(
            folder=folder,
            keywords=_split_csv(self.special_keywords_edit.text()),
            extensions=[item.lower().strip(". ") for item in _split_csv(self.special_extensions_edit.text())],
            pattern=self.special_pattern_edit.text().strip(),
            enable_subfolders=enable_subfolders,
            subfolders=subfolders,
        )
        self._apply_misc_settings()
        self._refresh_all()
        self.special_list.setCurrentRow(self.special_index + 2)
        self._on_special_select()

    def _apply_misc_settings(self):
        """Apply miscellaneous settings."""
        self.ruleset.misc_folder = self.misc_folder_edit.text().strip() or "90_零散文件"
        self.ruleset.other_subfolder = self.other_subfolder_edit.text().strip() or "其他文件"

    def _update_project_subfolder_editor_state(self):
        """Update project subfolder editor state."""
        enabled = self.enable_project_subfolders_check.isChecked()
        self.project_subfolders_text.setEnabled(enabled)
        if not enabled:
            self.project_subfolders_text.clear()

    def _update_special_subfolder_editor_state(self):
        """Update special subfolder editor state."""
        enabled = self.enable_special_subfolders_check.isChecked()
        self.special_subfolders_text.setEnabled(enabled)
        if not enabled:
            self.special_subfolders_text.clear()

    def _use_ai(self):
        """Use AI to generate rule suggestions."""
        if self.ai_running:
            self._append_chat_view("系统", "AI 仍在处理中，请稍候。")
            return

        prompt_text = self.ai_prompt.toPlainText().strip() or "请基于当前文件样本和已有规则，生成一版更合理的项目分类与特殊分类结构。"
        self._apply_misc_settings()
        reset_existing_results = self.ai_button.text() == "使用AI生成建议"

        self.ai_running = True
        self.ai_button.setEnabled(False)
        self.status_label.setText("正在请求 AI 生成建议，请稍候…")

        current_rules = deepcopy(self.ruleset)
        scanned_paths = [item.relative_path for item in self.scanned_files]
        self._append_chat("你", prompt_text)
        if reset_existing_results:
            self._append_chat_view("系统", "本轮会先清空上一次或示例项目结果，再按当前文件样本重新生成分类建议。")
        self._append_chat_view("系统", "已发起 API 请求，等待模型返回结果…")

        self.ai_thread = AIRulesThread(
            self.ai_service, scanned_paths, current_rules, prompt_text, self.chat_history, reset_existing_results
        )
        self.ai_thread.finished.connect(self._on_ai_success)
        self.ai_thread.error.connect(self._on_ai_failed)
        self.ai_thread.start()

    def _on_ai_success(self, suggested: Ruleset):
        """Handle AI success."""
        self.ai_running = False
        self.ruleset = suggested
        self._refresh_all()
        self.status_label.setText("AI 建议已载入。你可以继续手动调整后再保存。")
        self.ai_prompt.clear()
        self._append_chat(
            "AI",
            f"规则结构已更新，当前共有 {len(self.ruleset.projects)} 个项目规则，{len(self.ruleset.special_categories)} 个特殊分类。",
        )
        self.ai_button.setText("继续让AI调整")
        self.ai_button.setEnabled(True)

    def _on_ai_failed(self, exc: Exception):
        """Handle AI failure."""
        self.ai_running = False
        message = str(exc) if isinstance(exc, AIRulesError) else f"AI 请求失败：{exc}"
        self.status_label.setText(message)
        self._append_chat("系统", message)
        QMessageBox.critical(self, "AI 规则生成失败", message)
        self.ai_button.setEnabled(True)

    def _save_rules(self):
        """Save the rules."""
        if self.project_index is not None:
            self._save_project()
        if self.special_index is not None:
            self._save_special()
        self._apply_misc_settings()
        self.on_save(self.ruleset)
        self.status_label.setText("规则已保存，预览也已同步更新。")
        self._append_chat("系统", "规则已保存，当前预览已同步刷新。")
        self._refresh_preview_tree()
