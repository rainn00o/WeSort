"""PyQt6 main window for WeSort file organizer."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter

from gui_qt.qt_api_settings_window import APISettingsDialog
from gui_qt.qt_preview_window import PreviewDialog
from gui_qt.qt_rule_editor_window import RuleEditorDialog
from gui_qt.utils.threading import run_in_background
from models import PlanSummary, Ruleset, ScannedFile
from services.duplicates import DuplicateService
from services.executor import ExecutorService
from services.months import normalize_month_component
from services.planner import PlannerService
from services.rules import RuleRepository
from services.scanner import ScannerService
from services.ui_state import UIStateRepository


class GradientWidget(QWidget):
    """Widget with gradient background."""

    # Light blue-purple gradient colors
    GRADIENT_START = QColor(232, 240, 254)   # #E8F0FE - Light blue
    GRADIENT_MIDDLE = QColor(240, 230, 255)  # #F0E6FF - Light purple
    GRADIENT_END = QColor(232, 240, 254)     # #E8F0FE - Light blue

    def __init__(self, parent=None):
        super().__init__(parent)
        # Don't auto-fill - we'll paint the gradient ourselves
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        """Paint gradient background - light blue (top-left) to light purple (bottom-right)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Create diagonal gradient: top-left (light blue) to bottom-right (light purple)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, self.GRADIENT_START)   # Top-left: Light blue
        gradient.setColorAt(1.0, self.GRADIENT_MIDDLE)  # Bottom-right: Light purple

        painter.fillRect(self.rect(), gradient)


class FileOrganizerMainWindow(GradientWidget):
    """Main application window using PyQt6."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WeSort")
        self.resize(1200, 750)
        self.setMinimumSize(1000, 650)

        # Services
        self.state_repository = UIStateRepository()
        self.rule_repository = RuleRepository()
        self.scanner = ScannerService()
        self.duplicates = DuplicateService()
        self.planner = PlannerService()
        self.executor = ExecutorService()
        # State variables
        self.source_dir_text = ""
        self.target_dir_text = ""
        self.auto_duplicates = True
        self.add_month_prefix = True
        self.generate_report = True

        # Data
        self.scanned_files: list[ScannedFile] = []
        self.current_rules: Ruleset = self.rule_repository.load_active_rules()
        self.current_plan: PlanSummary | None = None
        self._busy = False
        self._scan_sort_column: int | None = None
        self._scan_sort_reverse = False

        # UI Components
        self.source_edit: QLineEdit | None = None
        self.target_edit: QLineEdit | None = None
        self.status_label: QLabel | None = None
        self.progress_bar: QProgressBar | None = None
        self.progress_label: QLabel | None = None
        self.file_table: QTreeWidget | None = None
        self.log_text: QTextEdit | None = None
        self.action_buttons: list[QPushButton] = []

        self._build_ui()
        self._load_state()

    def _build_ui(self) -> None:
        """Build the main UI layout - matching original Tkinter layout."""
        # Main vertical layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)  # Reduced from 12
        main_layout.setSpacing(6)  # Reduced from 8

        # Row 0: Path Frame (horizontal layout like original)
        path_frame = self._create_path_frame()
        main_layout.addWidget(path_frame)

        # Row 1: Options Frame
        options_frame = self._create_options_frame()
        main_layout.addWidget(options_frame)

        # Row 2: Button Frame (4 buttons horizontally)
        button_frame = self._create_button_frame()
        main_layout.addWidget(button_frame)

        # Row 3: Content Area (Splitter with table and log) - takes remaining space
        content_splitter = self._create_content_area()
        main_layout.addWidget(content_splitter, 1)

    def _create_path_frame(self) -> QGroupBox:
        """Create the directory selection frame - HORIZONTAL like original."""
        frame = QGroupBox("目录设置")
        # Use horizontal layout to match original grid layout
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)  # Reduced padding
        layout.setSpacing(6)  # Reduced spacing

        # Source directory: Label + Entry + Button
        source_label = QLabel("源目录")
        self.source_edit = QLineEdit()
        source_button = QPushButton("选择源目录")
        source_button.clicked.connect(self._choose_source_dir)
        source_button.setFixedWidth(90)  # Reduced from 100

        layout.addWidget(source_label)
        layout.addWidget(self.source_edit, 1)  # stretch=1
        layout.addWidget(source_button)

        # Spacer between source and target
        layout.addSpacing(12)  # Reduced from 16

        # Target directory: Label + Entry + Button
        target_label = QLabel("目标目录")
        self.target_edit = QLineEdit()
        target_button = QPushButton("选择目标目录")
        target_button.clicked.connect(self._choose_target_dir)
        target_button.setFixedWidth(90)  # Reduced from 100

        layout.addWidget(target_label)
        layout.addWidget(self.target_edit, 1)  # stretch=1
        layout.addWidget(target_button)

        frame.setLayout(layout)
        return frame

    def _create_options_frame(self) -> QGroupBox:
        """Create the runtime options frame - matching original layout."""
        frame = QGroupBox("运行选项")
        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)  # Reduced padding
        layout.setSpacing(6)  # Reduced spacing

        # Row 0: Checkboxes horizontally + API button on right
        checkboxes_row = QHBoxLayout()
        checkboxes_row.setSpacing(12)  # Reduced from 16

        self.auto_duplicates_check = QCheckBox("扫描后自动检测重复")
        self.auto_duplicates_check.setChecked(True)
        self.auto_duplicates_check.stateChanged.connect(
            lambda s: setattr(self, 'auto_duplicates', s == Qt.CheckState.Checked.value)
        )

        self.add_month_prefix_check = QCheckBox("分类时添加月份前缀")
        self.add_month_prefix_check.setChecked(True)
        self.add_month_prefix_check.stateChanged.connect(
            lambda s: setattr(self, 'add_month_prefix', s == Qt.CheckState.Checked.value)
        )

        self.generate_report_check = QCheckBox("分类完成后生成报告")
        self.generate_report_check.setChecked(True)
        self.generate_report_check.stateChanged.connect(
            lambda s: setattr(self, 'generate_report', s == Qt.CheckState.Checked.value)
        )

        checkboxes_row.addWidget(self.auto_duplicates_check)
        checkboxes_row.addWidget(self.add_month_prefix_check)
        checkboxes_row.addWidget(self.generate_report_check)
        checkboxes_row.addStretch()  # Push API button to right

        api_button = QPushButton("API设置")
        api_button.clicked.connect(self.open_api_settings)
        api_button.setFixedWidth(90)  # Reduced from 100
        checkboxes_row.addWidget(api_button)

        layout.addLayout(checkboxes_row)

        # Row 1: Status label
        self.status_label = QLabel("准备就绪")
        layout.addWidget(self.status_label)

        # Row 2: Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(16)  # Reduced from 20
        layout.addWidget(self.progress_bar)

        # Row 3: Progress text label
        self.progress_label = QLabel()
        layout.addWidget(self.progress_label)

        frame.setLayout(layout)
        return frame

    def _create_button_frame(self) -> QWidget:
        """Create the action buttons frame - 4 buttons HORIZONTAL like original."""
        frame = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(8, 0, 8, 6)  # Reduced padding
        layout.setSpacing(6)  # Reduced spacing

        scan_button = QPushButton("扫描文件")
        scan_button.clicked.connect(self.scan_files)
        layout.addWidget(scan_button, 1)  # Equal stretch
        self.action_buttons.append(scan_button)

        duplicate_button = QPushButton("重复文件处理")
        duplicate_button.clicked.connect(self.process_duplicates)
        layout.addWidget(duplicate_button, 1)
        self.action_buttons.append(duplicate_button)

        rules_button = QPushButton("AI辅助创建分类规则")
        rules_button.clicked.connect(self.open_rule_editor)
        layout.addWidget(rules_button, 1)
        self.action_buttons.append(rules_button)

        execute_button = QPushButton("执行文件分类")
        execute_button.clicked.connect(self.execute_plan)
        layout.addWidget(execute_button, 1)
        self.action_buttons.append(execute_button)

        frame.setLayout(layout)
        return frame

    def _create_content_area(self) -> QSplitter:
        """Create the main content area with table and log - VERTICAL like original."""
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Table frame (扫描结果)
        table_frame = QGroupBox("扫描结果")
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(12, 12, 12, 12)  # Reduced padding

        self.file_table = QTreeWidget()
        self.file_table.setHeaderLabels(["文件名", "月份目录", "扩展名", "大小（MB）"])
        self.file_table.setColumnWidth(0, 350)  # Reduced from 420
        self.file_table.setColumnWidth(1, 120)  # Reduced from 140
        self.file_table.setColumnWidth(2, 80)   # Reduced from 90
        self.file_table.setColumnWidth(3, 100)  # Reduced from 120
        self.file_table.setAlternatingRowColors(True)
        self.file_table.setRootIsDecorated(False)
        self.file_table.header().sectionClicked.connect(self._sort_scan_table)
        table_layout.addWidget(self.file_table)

        table_frame.setLayout(table_layout)
        splitter.addWidget(table_frame)

        # Log frame (运行日志)
        log_frame = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(12, 12, 12, 12)  # Reduced padding

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(120)  # Reduced from 150
        log_layout.addWidget(self.log_text)

        log_frame.setLayout(log_layout)
        splitter.addWidget(log_frame)

        # Set stretch factors (3:2 ratio like original)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        return splitter

    def _sort_scan_table(self, column: int) -> None:
        """Sort the scan table by column."""
        if self._scan_sort_column == column:
            self._scan_sort_reverse = not self._scan_sort_reverse
        else:
            self._scan_sort_column = column if column >= 0 else None
            self._scan_sort_reverse = False

        # Sort scanned_files based on column
        key_map = {
            0: lambda item: item.name.lower(),
            1: self._month_sort_key,
            2: self._extension_sort_key,
            3: lambda item: item.size,
        }

        sort_key = key_map.get(self._scan_sort_column if self._scan_sort_column is not None else 0, key_map[0])
        self.scanned_files.sort(key=sort_key, reverse=self._scan_sort_reverse)
        self._refresh_scan_table()

    def _month_sort_key(self, file_info: ScannedFile) -> tuple:
        """Sort key for month column."""
        month_display = self._resolve_scan_month_display(file_info)
        return (1 if month_display == "-" else 0, month_display)

    def _extension_sort_key(self, file_info: ScannedFile) -> tuple:
        """Sort key for extension column."""
        extension = (file_info.extension or "").lower()
        return (1 if not extension else 0, extension)

    def _choose_source_dir(self) -> None:
        """Open directory chooser for source."""
        path = QFileDialog.getExistingDirectory(self, "选择源目录")
        if path:
            self.source_edit.setText(path)
            self._save_state()

    def _choose_target_dir(self) -> None:
        """Open directory chooser for target."""
        path = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if path:
            self.target_edit.setText(path)
            self._save_state()

    def _append_log(self, message: str) -> None:
        """Append a message to the log text area."""
        self.log_text.append(message)

    def _set_busy(self, busy: bool, status_text: str | None = None) -> None:
        """Set the busy state and enable/disable buttons."""
        self._busy = busy
        for button in self.action_buttons:
            button.setEnabled(not busy)
        if status_text is not None:
            self.status_label.setText(status_text)
        if not busy:
            self._reset_progress()

    def _update_progress(self, current: int, total: int, message: str) -> None:
        """Update the progress bar and message."""
        safe_total = max(total, 1)
        value = 0 if total <= 0 else min(current, safe_total)
        self.progress_bar.setMaximum(safe_total)
        self.progress_bar.setValue(value)
        self.progress_label.setText(message)

    def _reset_progress(self) -> None:
        """Reset the progress bar."""
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_label.setText("")

    def _load_state(self) -> None:
        """Load UI state from repository."""
        state = self.state_repository.load()
        self.source_edit.setText(state.get("source_dir", ""))
        self.target_edit.setText(state.get("target_dir", ""))
        self.auto_duplicates = state.get("auto_duplicates", True)
        self.add_month_prefix = state.get("add_month_prefix", True)
        self.generate_report = state.get("generate_report", True)

        self.auto_duplicates_check.setChecked(self.auto_duplicates)
        self.add_month_prefix_check.setChecked(self.add_month_prefix)
        self.generate_report_check.setChecked(self.generate_report)

    def _save_state(self) -> None:
        """Save UI state to repository."""
        self.state_repository.save(
            {
                "source_dir": self.source_edit.text().strip(),
                "target_dir": self.target_edit.text().strip(),
                "auto_duplicates": self.auto_duplicates,
                "add_month_prefix": self.add_month_prefix,
                "generate_report": self.generate_report,
            }
        )

    def _require_source_dir(self) -> Path | None:
        """Check and return source directory if valid."""
        source = Path(self.source_edit.text().strip())
        if not source.exists() or not source.is_dir():
            QMessageBox.warning(self, "提示", "请先选择有效的源目录。")
            return None
        return source

    def _require_target_dir(self, silent: bool = False) -> Path | None:
        """Check and return target directory if valid."""
        target = Path(self.target_edit.text().strip())
        if not target.exists() or not target.is_dir():
            if not silent:
                QMessageBox.warning(self, "提示", "请先选择有效的目标目录。")
            return None
        return target

    def _refresh_scan_table(self) -> None:
        """Refresh the scan results table."""
        self.file_table.clear()
        for file_info in self.scanned_files:
            item = QTreeWidgetItem()
            item.setText(0, file_info.name)
            item.setText(1, self._resolve_scan_month_display(file_info))
            item.setText(2, file_info.extension or "-")
            item.setText(3, self._format_size_mb(file_info.size))
            self.file_table.addTopLevelItem(item)

    def _resolve_scan_month_display(self, file_info: ScannedFile) -> str:
        """Resolve the month display for a file."""
        if file_info.month_tag:
            return file_info.month_tag
        try:
            parent_parts = Path(file_info.relative_path).parent.parts
        except Exception:
            parent_parts = ()
        for part in reversed(parent_parts):
            normalized = normalize_month_component(part)
            if normalized:
                return normalized
        return "-"

    def _format_size_mb(self, size_bytes: int) -> str:
        """Format file size in MB."""
        size_mb = size_bytes / (1024 * 1024)
        if size_mb >= 100:
            return f"{size_mb:.0f}"
        if size_mb >= 10:
            return f"{size_mb:.1f}"
        return f"{size_mb:.2f}"

    def scan_files(self) -> None:
        """Scan files in the source directory."""
        source = self._require_source_dir()
        if source is None:
            return

        def task(signals):
            return self.scanner.scan(
                source,
                progress_callback=lambda c, t, m: signals.progress.emit(c, t, m)
            )

        def on_success(files: list[ScannedFile]) -> None:
            self.scanned_files = files
            self.current_plan = None
            self._refresh_scan_table()
            self.status_label.setText(f"扫描完成，共 {len(self.scanned_files)} 个文件")
            self._append_log(f"扫描完成：{source}，共 {len(self.scanned_files)} 个文件")
            self._save_state()
            if self.auto_duplicates:
                QTimer.singleShot(0, lambda: self.process_duplicates(auto_triggered=True, move_files=False))

        def on_error(exc: Exception) -> None:
            self.status_label.setText("扫描失败")
            self._append_log(f"扫描失败：{exc}")
            QMessageBox.critical(self, "扫描失败", str(exc))

        run_in_background(
            self,
            task,
            on_success,
            on_error,
            on_progress=self._update_progress,
            busy_callback=self._set_busy,
        )

    def process_duplicates(self, auto_triggered: bool = False, move_files: bool = True) -> None:
        """Process duplicate files."""
        if not self.scanned_files:
            if not auto_triggered:
                QMessageBox.information(self, "提示", "请先扫描文件。")
            return

        source = self._require_source_dir()
        if source is None:
            return

        target: Path | None = None
        if move_files:
            target = self._require_target_dir(silent=auto_triggered)
            if target is None:
                if auto_triggered:
                    self.status_label.setText("扫描完成，但未设置目标目录，已跳过自动重复检测")
                    self._append_log("已跳过自动重复检测：未设置有效的目标目录")
                return

        def task(signals):
            result = self.duplicates.scan_duplicates(
                [item.source_path for item in self.scanned_files],
                progress_callback=lambda c, t, m: signals.progress.emit(c, t, m)
            )
            if result.duplicate_count == 0:
                return ("none", result, None, None)
            if not move_files:
                return ("detected", result, None, None)
            trash_result = self.duplicates.move_duplicates_to_trash(
                result,
                target,
                progress_callback=lambda c, t, m: signals.progress.emit(c, t, m)
            )
            rescanned = self.scanner.scan(
                source,
                progress_callback=lambda c, t, m: signals.progress.emit(c, t, m)
            )
            return ("moved", result, trash_result, rescanned)

        def on_success(payload) -> None:
            mode, result, trash_result, rescanned = payload
            if mode == "none":
                self.status_label.setText("未发现重复文件")
                self._append_log("重复检测完成：未发现重复文件")
            elif mode == "detected":
                self.status_label.setText(f"检测到 {len(result.groups)} 组重复文件，请点击「重复文件处理」执行移动")
                self._append_log(
                    f"自动重复检测完成：发现 {len(result.groups)} 组重复文件，共 {result.duplicate_count} 个重复文件，尚未移动"
                )
            else:
                self.scanned_files = rescanned or self.scanned_files
                self._refresh_scan_table()
                self.status_label.setText(f"重复处理完成，已移动 {trash_result.moved_count} 个文件")
                self._append_log(
                    f"重复处理完成：共 {len(result.groups)} 组，移动 {trash_result.moved_count} 个文件到 {trash_result.trash_dir}"
                )

        def on_error(exc: Exception) -> None:
            if not auto_triggered:
                self.status_label.setText("重复文件处理失败")
                self._append_log(f"重复文件处理失败：{exc}")
                QMessageBox.critical(self, "重复文件处理失败", str(exc))

        busy_text = "正在处理重复文件…" if move_files else "正在检测重复文件…"
        run_in_background(
            self,
            task,
            on_success,
            on_error,
            on_progress=self._update_progress,
            busy_callback=lambda b: self._set_busy(b, busy_text if b else None),
        )

    def open_api_settings(self) -> None:
        """Open the API settings dialog."""
        dialog = APISettingsDialog(self)
        dialog.exec()

    def open_rule_editor(self) -> None:
        """Open the rule editor dialog."""
        self._refresh_rules()

        def _on_save(ruleset: Ruleset) -> None:
            try:
                self.rule_repository.save_generated_rules(ruleset)
                self.current_rules = ruleset
                self.current_plan = None
                self.status_label.setText("规则已保存")
                self._append_log("分类规则已保存到 config/rules_generated.json")
            except Exception as exc:
                self.status_label.setText("保存规则失败")
                QMessageBox.critical(self, "保存分类规则失败", str(exc))
                raise

        dialog = RuleEditorDialog(
            parent=self,
            ruleset=self.current_rules,
            scanned_files=self.scanned_files,
            add_month_prefix=self.add_month_prefix,
            on_save=_on_save,
        )
        dialog.exec()

    def _refresh_rules(self) -> None:
        """Refresh the current rules from repository."""
        self.current_rules = self.rule_repository.load_active_rules()

    def _build_plan(self) -> PlanSummary | None:
        """Build a classification plan."""
        if not self.scanned_files:
            QMessageBox.information(self, "提示", "请先扫描文件。")
            return None

        try:
            self.current_rules = self.rule_repository.load_active_rules()
            plan = self.planner.build_plan(
                files=self.scanned_files,
                ruleset=self.current_rules,
                add_month_prefix=self.add_month_prefix,
            )
        except Exception as exc:
            self.status_label.setText("生成分类计划失败")
            QMessageBox.critical(self, "生成分类计划失败", str(exc))
            return None

        self.current_plan = plan
        return plan

    def execute_plan(self) -> None:
        """Execute the file classification plan."""
        plan = self._build_plan()
        if plan is None:
            return

        target = self._require_target_dir()
        if target is None:
            return

        reply = QMessageBox.question(
            self,
            "确认",
            "执行后会移动文件到目标目录，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        source = self._require_source_dir()
        if source is None:
            return

        def task(signals):
            result = self.executor.execute(
                plan=plan,
                output_root=target,
                generate_report=self.generate_report,
            )
            rescanned = self.scanner.scan(source)
            return result, rescanned

        def on_success(payload) -> None:
            result, rescanned = payload
            self.scanned_files = rescanned
            self._refresh_scan_table()
            self.status_label.setText(f"分类完成：成功 {result.moved_count}，失败 {result.failed_count}")
            self._append_log(f"分类完成：成功 {result.moved_count}，失败 {result.failed_count}")
            if result.report_txt:
                self._append_log(f"分类报告：{result.report_txt}")

        def on_error(exc: Exception) -> None:
            self.status_label.setText("执行文件分类失败")
            QMessageBox.critical(self, "执行文件分类失败", str(exc))

        run_in_background(
            self,
            task,
            on_success,
            on_error,
            on_progress=self._update_progress,
            busy_callback=lambda b: self._set_busy(b, "正在执行文件分类…" if b else None),
        )
