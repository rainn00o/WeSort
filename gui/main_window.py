from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from gui.api_settings_window import APISettingsWindow
from gui.preview_window import PreviewWindow
from gui.rule_editor_window import RuleEditorWindow
from models import PlanSummary, Ruleset, ScannedFile
from services.duplicates import DuplicateService
from services.executor import ExecutorService
from services.logging_utils import StepLogger
from services.months import normalize_month_component
from services.planner import PlannerService
from services.rules import RuleRepository
from services.scanner import ScannerService
from services.ui_state import UIStateRepository


class FileOrganizerGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("WeSort")
        self.root.geometry("1360x900")
        self.root.minsize(1180, 760)

        self.state_repository = UIStateRepository()
        self.rule_repository = RuleRepository()
        self.scanner = ScannerService()
        self.duplicates = DuplicateService()
        self.planner = PlannerService()
        self.executor = ExecutorService()
        self.step_logger = StepLogger()

        self.source_dir_var = tk.StringVar()
        self.target_dir_var = tk.StringVar()
        self.auto_duplicates_var = tk.BooleanVar(value=True)
        self.add_month_prefix_var = tk.BooleanVar(value=True)
        self.generate_report_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="准备就绪")
        self.progress_text_var = tk.StringVar(value="")

        self.scanned_files: list[ScannedFile] = []
        self.current_rules: Ruleset = self.rule_repository.load_active_rules()
        self.current_plan: PlanSummary | None = None
        self._busy = False
        self._action_buttons: list[ttk.Button] = []
        self._scan_sort_column: str | None = None
        self._scan_sort_reverse = False

        self._build_ui()
        self._load_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(3, weight=1)

        path_frame = ttk.LabelFrame(self.root, text="目录设置", padding=12)
        path_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))
        path_frame.columnconfigure(1, weight=1)
        path_frame.columnconfigure(4, weight=1)
        ttk.Label(path_frame, text="源目录").grid(row=0, column=0, sticky="w")
        ttk.Entry(path_frame, textvariable=self.source_dir_var).grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(path_frame, text="选择源目录", command=self._choose_source_dir).grid(row=0, column=2, sticky="ew")
        ttk.Label(path_frame, text="目标目录").grid(row=0, column=3, sticky="w", padx=(16, 0))
        ttk.Entry(path_frame, textvariable=self.target_dir_var).grid(row=0, column=4, sticky="ew", padx=(8, 8))
        ttk.Button(path_frame, text="选择目标目录", command=self._choose_target_dir).grid(row=0, column=5, sticky="ew")

        options_frame = ttk.LabelFrame(self.root, text="运行选项", padding=12)
        options_frame.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        options_frame.columnconfigure(4, weight=1)
        ttk.Checkbutton(options_frame, text="扫描后自动检测重复", variable=self.auto_duplicates_var).grid(row=0, column=0, sticky="w", padx=(0, 20))
        ttk.Checkbutton(options_frame, text="分类时添加月份前缀", variable=self.add_month_prefix_var).grid(row=0, column=1, sticky="w", padx=(0, 20))
        ttk.Checkbutton(options_frame, text="分类完成后生成报告", variable=self.generate_report_var).grid(row=0, column=2, sticky="w")
        ttk.Button(options_frame, text="API设置", command=self.open_api_settings).grid(row=0, column=4, sticky="e")
        ttk.Label(options_frame, textvariable=self.status_var).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.progress_bar = ttk.Progressbar(options_frame, mode="determinate", maximum=100, value=0)
        self.progress_bar.grid(row=2, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        ttk.Label(options_frame, textvariable=self.progress_text_var).grid(row=3, column=0, columnspan=5, sticky="w", pady=(6, 0))

        button_frame = ttk.Frame(self.root, padding=(12, 0, 12, 8))
        button_frame.grid(row=2, column=0, sticky="ew")
        for index in range(4):
            button_frame.columnconfigure(index, weight=1)
        scan_button = ttk.Button(button_frame, text="扫描文件", command=self.scan_files)
        scan_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        duplicate_button = ttk.Button(button_frame, text="重复文件处理", command=self.process_duplicates)
        duplicate_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        rules_button = ttk.Button(button_frame, text="AI辅助创建分类规则", command=self.open_rule_editor)
        rules_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        execute_button = ttk.Button(button_frame, text="执行文件分类", command=self.execute_plan)
        execute_button.grid(row=0, column=3, sticky="ew")
        self._action_buttons = [scan_button, duplicate_button, rules_button, execute_button]

        content = ttk.Panedwindow(self.root, orient=tk.VERTICAL)
        content.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))

        table_frame = ttk.LabelFrame(content, text="扫描结果", padding=12)
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        columns = ("name", "month_tag", "extension", "size")
        self.file_table = ttk.Treeview(table_frame, columns=columns, show="headings")
        headings = {
            "name": "文件名",
            "month_tag": "月份目录",
            "extension": "扩展名",
            "size": "大小（MB）",
        }
        widths = {
            "name": 420,
            "month_tag": 140,
            "extension": 90,
            "size": 120,
        }
        for column in columns:
            self.file_table.heading(
                column,
                text=headings[column],
                command=lambda current=column: self._sort_scan_table(current),
            )
            self.file_table.column(column, width=widths[column], anchor=tk.W)
        self.file_table.grid(row=0, column=0, sticky="nsew")
        file_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.file_table.yview)
        file_scroll.grid(row=0, column=1, sticky="ns")
        self.file_table.configure(yscrollcommand=file_scroll.set)
        content.add(table_frame, weight=3)

        log_frame = ttk.LabelFrame(content, text="运行日志", padding=12)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=12, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.configure(selectbackground="#cfe8ff", selectforeground="#000000")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        content.add(log_frame, weight=2)

    def _choose_source_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.source_dir_var.set(path)
            self._save_state()

    def _choose_target_dir(self) -> None:
        path = filedialog.askdirectory(parent=self.root)
        if path:
            self.target_dir_var.set(path)
            self._save_state()

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _set_busy(self, busy: bool, status_text: str | None = None) -> None:
        self._busy = busy
        for button in self._action_buttons:
            if busy:
                button.state(["disabled"])
            else:
                button.state(["!disabled"])
        if status_text is not None:
            self.status_var.set(status_text)
        if not busy:
            self._reset_progress()

    def _update_progress(self, current: int, total: int, message: str) -> None:
        safe_total = max(total, 1)
        value = 0 if total <= 0 else min(current, safe_total)
        self.progress_bar.configure(mode="determinate", maximum=safe_total)
        self.progress_bar["value"] = value
        self.progress_text_var.set(message)

    def _reset_progress(self) -> None:
        self.progress_bar.configure(mode="determinate", maximum=100)
        self.progress_bar["value"] = 0
        self.progress_text_var.set("")

    def _run_in_background(
        self,
        busy_text: str,
        task,
        on_success,
        on_error,
    ) -> None:
        if self._busy:
            self._append_log("当前仍有任务在执行，请稍候。")
            return
        self._set_busy(True, busy_text)

        def worker() -> None:
            try:
                result = task()
            except Exception as exc:  # noqa: BLE001
                self.root.after(0, lambda exc=exc: self._finish_background_error(exc, on_error))
                return
            self.root.after(0, lambda result=result: self._finish_background_success(result, on_success))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_background_success(self, result, on_success) -> None:
        self._set_busy(False)
        on_success(result)

    def _finish_background_error(self, exc: Exception, on_error) -> None:
        self._set_busy(False)
        on_error(exc)

    def _handle_step_error(
        self,
        step_name: str,
        title: str,
        exc: Exception,
        context: dict | None = None,
        status_text: str | None = None,
    ) -> None:
        self.step_logger.write_error(step_name, exc, context=context)
        self.status_var.set(status_text or f"{title}失败")
        self._append_log(f"{title}失败：{exc}")
        messagebox.showerror(f"{title}失败", str(exc), parent=self.root)

    def _rescan_source_quietly(self) -> None:
        source = self._require_source_dir()
        if source is None:
            return
        self.scanned_files = self.scanner.scan(source)

    def open_api_settings(self) -> None:
        dialog = APISettingsWindow(self.root)
        dialog.transient(self.root)
        dialog.grab_set()

    def _load_state(self) -> None:
        state = self.state_repository.load()
        self.source_dir_var.set(state.get("source_dir", ""))
        self.target_dir_var.set(state.get("target_dir", ""))
        self.auto_duplicates_var.set(state.get("auto_duplicates", True))
        self.add_month_prefix_var.set(state.get("add_month_prefix", True))
        self.generate_report_var.set(state.get("generate_report", True))
        geometry = state.get("geometry")
        if geometry:
            self.root.geometry(geometry)

    def _save_state(self) -> None:
        self.state_repository.save(
            {
                "source_dir": self.source_dir_var.get().strip(),
                "target_dir": self.target_dir_var.get().strip(),
                "auto_duplicates": self.auto_duplicates_var.get(),
                "add_month_prefix": self.add_month_prefix_var.get(),
                "generate_report": self.generate_report_var.get(),
                "geometry": self.root.winfo_geometry(),
            }
        )

    def _on_close(self) -> None:
        self._save_state()
        self.root.destroy()

    def _require_source_dir(self) -> Path | None:
        source = Path(self.source_dir_var.get().strip())
        if not source.exists() or not source.is_dir():
            messagebox.showwarning("提示", "请先选择有效的源目录。", parent=self.root)
            return None
        return source

    def _require_target_dir(self, silent: bool = False) -> Path | None:
        target = Path(self.target_dir_var.get().strip())
        if not target.exists() or not target.is_dir():
            if not silent:
                messagebox.showwarning("提示", "请先选择有效的目标目录。", parent=self.root)
            return None
        return target

    def _refresh_scan_table(self) -> None:
        self._sort_scanned_files()
        self.file_table.delete(*self.file_table.get_children())
        for file_info in self.scanned_files:
            self.file_table.insert(
                "",
                tk.END,
                values=(
                    file_info.name,
                    self._resolve_scan_month_display(file_info),
                    file_info.extension or "-",
                    self._format_size_mb(file_info.size),
                ),
            )
        self._refresh_scan_table_headings()

    def _refresh_scan_table_headings(self) -> None:
        labels = {
            "name": "文件名",
            "month_tag": "月份目录",
            "extension": "扩展名",
            "size": "大小（MB）",
        }
        for column, label in labels.items():
            if column == self._scan_sort_column:
                arrow = " ↓" if self._scan_sort_reverse else " ↑"
                self.file_table.heading(column, text=label + arrow, command=lambda current=column: self._sort_scan_table(current))
            else:
                self.file_table.heading(column, text=label, command=lambda current=column: self._sort_scan_table(current))

    def _sort_scan_table(self, column: str) -> None:
        if self._scan_sort_column == column:
            self._scan_sort_reverse = not self._scan_sort_reverse
        else:
            self._scan_sort_column = column
            self._scan_sort_reverse = False
        self._refresh_scan_table()

    def _sort_scanned_files(self) -> None:
        key_map = {
            "name": lambda item: item.name.lower(),
            "month_tag": self._month_sort_key,
            "extension": self._extension_sort_key,
            "size": lambda item: item.size,
        }
        sort_key = key_map.get(self._scan_sort_column or "name", key_map["name"])
        self.scanned_files.sort(key=sort_key, reverse=self._scan_sort_reverse)

    def _month_sort_key(self, file_info: ScannedFile) -> tuple[int, str]:
        month_display = self._resolve_scan_month_display(file_info)
        return (1 if month_display == "-" else 0, month_display)

    def _extension_sort_key(self, file_info: ScannedFile) -> tuple[int, str]:
        extension = (file_info.extension or "").lower()
        return (1 if not extension else 0, extension)

    def _resolve_scan_month_display(self, file_info: ScannedFile) -> str:
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
        size_mb = size_bytes / (1024 * 1024)
        if size_mb >= 100:
            return f"{size_mb:.0f}"
        if size_mb >= 10:
            return f"{size_mb:.1f}"
        return f"{size_mb:.2f}"

    def _refresh_rules(self) -> None:
        self.current_rules = self.rule_repository.load_active_rules()

    def scan_files(self) -> None:
        source = self._require_source_dir()
        if source is None:
            return
        self.root.update_idletasks()

        def task() -> list[ScannedFile]:
            return self.scanner.scan(
                source,
                progress_callback=lambda current, total, message: self.root.after(
                    0, self._update_progress, current, total, message
                ),
            )

        def on_success(files: list[ScannedFile]) -> None:
            self.scanned_files = files
            self.current_plan = None
            self._refresh_scan_table()
            self.status_var.set(f"扫描完成，共 {len(self.scanned_files)} 个文件")
            self._append_log(f"扫描完成：{source}，共 {len(self.scanned_files)} 个文件")
            self.step_logger.write(
                "scan_summary",
                {
                    "source_dir": str(source),
                    "file_count": len(self.scanned_files),
                    "month_tagged_files": sum(1 for item in self.scanned_files if item.month_tag),
                },
            )
            self._save_state()
            if self.auto_duplicates_var.get():
                self.root.after(0, lambda: self.process_duplicates(auto_triggered=True, move_files=False))

        def on_error(exc: Exception) -> None:
            self._handle_step_error(
                "scan",
                "扫描",
                exc,
                context={"source_dir": str(source)},
                status_text="扫描失败",
            )

        self._run_in_background("正在扫描文件…", task, on_success, on_error)

    def process_duplicates(self, auto_triggered: bool = False, move_files: bool = True) -> None:
        if not self.scanned_files:
            if not auto_triggered:
                messagebox.showinfo("提示", "请先扫描文件。", parent=self.root)
            return
        source = self._require_source_dir()
        if source is None:
            return
        target: Path | None = None
        if move_files:
            target = self._require_target_dir(silent=auto_triggered)
            if target is None:
                if auto_triggered:
                    self.status_var.set("扫描完成，但未设置目标目录，已跳过自动重复检测")
                    self._append_log("已跳过自动重复检测：未设置有效的目标目录")
                return

        def task() -> tuple[str, object, object | None, list[ScannedFile] | None]:
            result = self.duplicates.scan_duplicates(
                [item.source_path for item in self.scanned_files],
                progress_callback=lambda current, total, message: self.root.after(
                    0, self._update_progress, current, total, message
                ),
            )
            if result.duplicate_count == 0:
                return ("none", result, None, None)
            if not move_files:
                return ("detected", result, None, None)
            trash_result = self.duplicates.move_duplicates_to_trash(
                result,
                target,
                progress_callback=lambda current, total, message: self.root.after(
                    0, self._update_progress, current, total, message
                ),
            )
            rescanned = self.scanner.scan(
                source,
                progress_callback=lambda current, total, message: self.root.after(
                    0, self._update_progress, current, total, message
                ),
            )
            return ("moved", result, trash_result, rescanned)

        def on_success(payload: tuple[str, object, object | None, list[ScannedFile] | None]) -> None:
            mode, result, trash_result, rescanned = payload
            if mode == "none":
                self.status_var.set("未发现重复文件")
                self._append_log("重复检测完成：未发现重复文件")
                self.step_logger.write(
                    "duplicate_summary",
                    {
                        "scanned_files": result.total_files,
                        "duplicate_groups": 0,
                        "duplicate_files": 0,
                    },
                )
                return
            if mode == "detected":
                self.status_var.set(f"检测到 {len(result.groups)} 组重复文件，请点击“重复文件处理”执行移动")
                self._append_log(
                    f"自动重复检测完成：发现 {len(result.groups)} 组重复文件，共 {result.duplicate_count} 个重复文件，尚未移动"
                )
                self.step_logger.write(
                    "duplicate_summary",
                    {
                        "duplicate_groups": len(result.groups),
                        "duplicate_files": result.duplicate_count,
                        "action": "detect_only",
                    },
                )
                return
            self.scanned_files = rescanned or self.scanned_files
            self._refresh_scan_table()
            self.status_var.set(f"重复处理完成，已移动 {trash_result.moved_count} 个文件")
            self._append_log(
                f"重复处理完成：共 {len(result.groups)} 组，移动 {trash_result.moved_count} 个文件到 {trash_result.trash_dir}"
            )
            self.step_logger.write(
                "duplicate_summary",
                {
                    "duplicate_groups": len(result.groups),
                    "duplicate_files": result.duplicate_count,
                    "moved_count": trash_result.moved_count,
                    "failed_count": trash_result.failed_count,
                    "trash_dir": str(trash_result.trash_dir),
                    "csv_path": str(trash_result.csv_path),
                },
            )

        def on_error(exc: Exception) -> None:
            if not auto_triggered:
                self._handle_step_error(
                    "duplicate",
                    "重复文件处理",
                    exc,
                    context={
                        "source_dir": self.source_dir_var.get().strip(),
                        "target_dir": str(target) if target else "",
                        "file_count": len(self.scanned_files),
                    },
                    status_text="重复文件处理失败",
                )
            else:
                self.step_logger.write_error(
                    "duplicate",
                    exc,
                    context={
                        "source_dir": self.source_dir_var.get().strip(),
                        "target_dir": str(target) if target else "",
                        "file_count": len(self.scanned_files),
                        "auto_triggered": True,
                        "move_files": move_files,
                    },
                )
                self.status_var.set("自动重复文件处理失败")
                self._append_log(f"自动重复文件处理失败：{exc}")

        busy_text = "正在处理重复文件…" if move_files else "正在检测重复文件…"
        self._run_in_background(busy_text, task, on_success, on_error)

    def open_rule_editor(self) -> None:
        self._refresh_rules()

        def _on_save(ruleset: Ruleset) -> None:
            try:
                self.rule_repository.save_generated_rules(ruleset)
                self.current_rules = ruleset
                self.current_plan = None
                self.status_var.set("规则已保存")
                self._append_log("分类规则已保存到 config/rules_generated.json")
                self.step_logger.write(
                    "rules_summary",
                    {
                        "project_count": len(ruleset.projects),
                        "special_category_count": len(ruleset.special_categories),
                        "generated_rules_path": "config/rules_generated.json",
                    },
                )
            except Exception as exc:
                self._handle_step_error(
                    "rules",
                    "保存分类规则",
                    exc,
                    context={
                        "project_count": len(ruleset.projects),
                        "special_category_count": len(ruleset.special_categories),
                    },
                    status_text="保存规则失败",
                )
                raise

        dialog = RuleEditorWindow(
            master=self.root,
            ruleset=self.current_rules,
            scanned_files=self.scanned_files,
            add_month_prefix=self.add_month_prefix_var.get(),
            on_save=_on_save,
        )
        dialog.transient(self.root)
        dialog.grab_set()

    def _build_plan(self) -> PlanSummary | None:
        if not self.scanned_files:
            messagebox.showinfo("提示", "请先扫描文件。", parent=self.root)
            return None
        try:
            self._refresh_rules()
            plan = self.planner.build_plan(
                files=self.scanned_files,
                ruleset=self.current_rules,
                add_month_prefix=self.add_month_prefix_var.get(),
            )
        except Exception as exc:
            self._handle_step_error(
                "plan",
                "生成分类计划",
                exc,
                context={
                    "file_count": len(self.scanned_files),
                    "add_month_prefix": self.add_month_prefix_var.get(),
                },
                status_text="生成分类计划失败",
            )
            return None
        self.current_plan = plan
        return plan

    def preview_plan(self) -> None:
        plan = self._build_plan()
        if plan is None:
            return
        try:
            PreviewWindow(self.root, plan)
            self.status_var.set(f"预览完成，共 {plan.total_files} 个文件")
            self._append_log(f"已生成分类预览，共 {plan.total_files} 个文件")
            self.step_logger.write(
                "preview_summary",
                {
                    "file_count": plan.total_files,
                    "top_folder_count": len(plan.top_folders),
                },
            )
        except Exception as exc:
            self._handle_step_error(
                "preview",
                "预览分类",
                exc,
                context={"file_count": plan.total_files},
                status_text="预览分类失败",
            )

    def execute_plan(self) -> None:
        plan = self._build_plan()
        if plan is None:
            return
        target = self._require_target_dir()
        if target is None:
            return
        if not messagebox.askyesno("确认", "执行后会移动文件到目标目录，是否继续？", parent=self.root):
            return
        source = self._require_source_dir()
        if source is None:
            return

        def task():
            result = self.executor.execute(
                plan=plan,
                output_root=target,
                generate_report=self.generate_report_var.get(),
            )
            rescanned = self.scanner.scan(source)
            return result, rescanned

        def on_success(payload) -> None:
            result, rescanned = payload
            self.scanned_files = rescanned
            self._refresh_scan_table()
            self.status_var.set(f"分类完成：成功 {result.moved_count}，失败 {result.failed_count}")
            self._append_log(f"分类完成：成功 {result.moved_count}，失败 {result.failed_count}")
            if result.report_txt:
                self._append_log(f"分类报告：{result.report_txt}")
            self.step_logger.write(
                "classification_summary",
                {
                    "output_root": str(result.output_root),
                    "moved_count": result.moved_count,
                    "failed_count": result.failed_count,
                    "report_txt": str(result.report_txt) if result.report_txt else "",
                },
            )

        def on_error(exc: Exception) -> None:
            self._handle_step_error(
                "classification",
                "执行文件分类",
                exc,
                context={
                    "output_root": str(target),
                    "file_count": plan.total_files,
                    "generate_report": self.generate_report_var.get(),
                },
                status_text="执行文件分类失败",
            )

        self._run_in_background("正在执行文件分类…", task, on_success, on_error)

    def run(self) -> None:
        self.root.mainloop()
