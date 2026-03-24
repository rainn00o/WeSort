from __future__ import annotations

import threading
import tkinter as tk
from collections import defaultdict
from copy import deepcopy
from tkinter import messagebox, ttk

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


def _subfolders_to_text(subfolders: list[ProjectSubfolderRule] | list[SpecialSubfolderRule]) -> str:
    lines: list[str] = []
    for subfolder in subfolders:
        lines.append(f"{subfolder.name}:{','.join(subfolder.keywords)}|{','.join(subfolder.extensions)}")
    return "\n".join(lines)


def _project_subfolders_from_text(value: str) -> list[ProjectSubfolderRule]:
    result: list[ProjectSubfolderRule] = []
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


def _special_subfolders_from_text(value: str) -> list[SpecialSubfolderRule]:
    result: list[SpecialSubfolderRule] = []
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


class RuleEditorWindow(tk.Toplevel):
    def __init__(
        self,
        master: tk.Misc,
        ruleset: Ruleset,
        scanned_files: list[ScannedFile],
        add_month_prefix: bool,
        on_save,
    ) -> None:
        super().__init__(master)
        self.title("AI辅助创建分类规则")
        self.geometry("1280x860")

        self.ruleset = deepcopy(ruleset)
        self.scanned_files = list(scanned_files)
        self.add_month_prefix = add_month_prefix
        self.on_save = on_save

        self.ai_service = AIRulesService()
        self.planner = PlannerService()
        self.project_index: int | None = None
        self.special_index: int | None = None
        self.preview_lookup: dict[tuple[str, str], list[PlanItem]] = {}
        self.chat_history: list[tuple[str, str]] = []
        self.ai_running = False

        self._build_ui()
        self._refresh_all()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        outer = ttk.Frame(self, padding=12)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.grid(row=0, column=0, sticky="nsew")

        self.project_tab = ttk.Frame(notebook, padding=12)
        self.project_tab.columnconfigure(1, weight=1)
        self.project_tab.rowconfigure(0, weight=1)
        notebook.add(self.project_tab, text="项目分类")
        self._build_project_tab()

        self.special_tab = ttk.Frame(notebook, padding=12)
        self.special_tab.columnconfigure(1, weight=1)
        self.special_tab.rowconfigure(0, weight=1)
        notebook.add(self.special_tab, text="特殊分类")
        self._build_special_tab()

        self.preview_tab = ttk.Frame(notebook, padding=12)
        self.preview_tab.columnconfigure(1, weight=1)
        self.preview_tab.rowconfigure(0, weight=1)
        notebook.add(self.preview_tab, text="命中文件预览")
        self._build_preview_tab()

        bottom = ttk.LabelFrame(outer, text="AI辅助与保存", padding=12)
        bottom.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        bottom.columnconfigure(0, weight=1)

        ttk.Label(bottom, text="对话记录").grid(row=0, column=0, sticky="w")
        self.chat_text = tk.Text(bottom, height=8, wrap="word")
        self.chat_text.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 8))
        self.chat_text.configure(selectbackground="#cfe8ff", selectforeground="#000000", state="disabled")
        self.chat_text.tag_configure("role_system", foreground="#666666")
        self.chat_text.tag_configure("role_user", foreground="#0b3d91")
        self.chat_text.tag_configure("role_ai", foreground="#1f6f43")

        ttk.Label(bottom, text="补充要求").grid(row=2, column=0, sticky="w")
        preset_bar = ttk.Frame(bottom)
        preset_bar.grid(row=2, column=1, columnspan=3, sticky="e")
        self.preset_prompt_var = tk.StringVar(value="生成初版规则")
        self.preset_prompt_combo = ttk.Combobox(
            preset_bar,
            state="readonly",
            textvariable=self.preset_prompt_var,
            values=list(PRESET_AI_PROMPTS.keys()),
            width=20,
        )
        self.preset_prompt_combo.grid(row=0, column=0, padx=(0, 8))
        ttk.Button(preset_bar, text="插入预设提示词", command=self._insert_preset_prompt).grid(row=0, column=1)

        self.ai_prompt = tk.Text(bottom, height=4, wrap="word")
        self.ai_prompt.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(6, 8))
        self.ai_prompt.configure(selectbackground="#cfe8ff", selectforeground="#000000")

        self.status_var = tk.StringVar(value="你可以直接编辑规则，也可以先让 AI 生成建议。")
        ttk.Label(bottom, textvariable=self.status_var).grid(row=4, column=0, sticky="w")
        self.ai_button = ttk.Button(bottom, text="使用AI生成建议", command=self._use_ai)
        self.ai_button.grid(row=4, column=2, sticky="e", padx=(8, 0))
        ttk.Button(bottom, text="保存规则", command=self._save_rules).grid(row=4, column=3, sticky="e", padx=(8, 0))

        self._append_chat("系统", "你可以先让 AI 生成一版规则，然后继续输入要求来调整当前结构。")

    def _build_project_tab(self) -> None:
        left = ttk.Frame(self.project_tab)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="项目列表").grid(row=0, column=0, sticky="w")
        self.project_list = tk.Listbox(left, width=36, exportselection=False)
        self.project_list.grid(row=1, column=0, sticky="nsw", pady=(6, 8))
        self.project_list.bind("<<ListboxSelect>>", self._on_project_select)
        ttk.Button(left, text="新增项目", command=self._add_project).grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(left, text="删除项目", command=self._delete_project).grid(row=3, column=0, sticky="ew")

        form = ttk.Frame(self.project_tab)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(5, weight=1)

        ttk.Label(form, text="项目名称").grid(row=0, column=0, sticky="w")
        self.project_name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.project_name_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="目录名称").grid(row=1, column=0, sticky="w")
        self.project_folder_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.project_folder_var).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="关键词（逗号分隔）").grid(row=2, column=0, sticky="w")
        self.project_keywords_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.project_keywords_var).grid(row=2, column=1, sticky="ew", pady=(0, 8))

        self.enable_project_subfolders_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form,
            text="启用项目子目录细分",
            variable=self.enable_project_subfolders_var,
            command=self._update_project_subfolder_editor_state,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(form, text="项目子目录规则（每行：子目录:关键词1,关键词2|ext1,ext2）").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )
        self.project_subfolders_text = tk.Text(form, height=8, wrap="word")
        self.project_subfolders_text.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(6, 8))
        self.project_subfolders_text.configure(selectbackground="#cfe8ff", selectforeground="#000000")
        ttk.Button(form, text="保存当前项目", command=self._save_project).grid(row=6, column=1, sticky="e")
        self._update_project_subfolder_editor_state()

    def _build_special_tab(self) -> None:
        left = ttk.Frame(self.special_tab)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="特殊分类列表").grid(row=0, column=0, sticky="w")
        self.special_list = tk.Listbox(left, width=36, exportselection=False)
        self.special_list.grid(row=1, column=0, sticky="nsw", pady=(6, 8))
        self.special_list.bind("<<ListboxSelect>>", self._on_special_select)
        ttk.Button(left, text="新增特殊分类", command=self._add_special).grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(left, text="删除特殊分类", command=self._delete_special).grid(row=3, column=0, sticky="ew")

        form = ttk.Frame(self.special_tab)
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        form.rowconfigure(6, weight=1)

        ttk.Label(form, text="目录名称").grid(row=0, column=0, sticky="w")
        self.special_folder_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.special_folder_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="关键词（逗号分隔）").grid(row=1, column=0, sticky="w")
        self.special_keywords_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.special_keywords_var).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="扩展名（逗号分隔）").grid(row=2, column=0, sticky="w")
        self.special_extensions_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.special_extensions_var).grid(row=2, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="正则表达式").grid(row=3, column=0, sticky="w")
        self.special_pattern_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.special_pattern_var).grid(row=3, column=1, sticky="ew", pady=(0, 8))

        self.enable_special_subfolders_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form,
            text="启用特殊分类子目录细分",
            variable=self.enable_special_subfolders_var,
            command=self._update_special_subfolder_editor_state,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(form, text="特殊分类子目录规则（每行：子目录:关键词1,关键词2|ext1,ext2）").grid(
            row=5, column=0, columnspan=2, sticky="w"
        )
        self.special_subfolders_text = tk.Text(form, height=10, wrap="word")
        self.special_subfolders_text.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(6, 8))
        self.special_subfolders_text.configure(selectbackground="#cfe8ff", selectforeground="#000000")
        ttk.Button(form, text="保存当前特殊分类", command=self._save_special).grid(row=7, column=1, sticky="e")
        self._update_special_subfolder_editor_state()

        misc_frame = ttk.LabelFrame(form, text="兜底目录设置", padding=8)
        misc_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        misc_frame.columnconfigure(1, weight=1)
        ttk.Label(misc_frame, text="零散文件目录").grid(row=0, column=0, sticky="w")
        self.misc_folder_var = tk.StringVar()
        ttk.Entry(misc_frame, textvariable=self.misc_folder_var).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(misc_frame, text="默认细分类名称").grid(row=1, column=0, sticky="w")
        self.other_subfolder_var = tk.StringVar()
        ttk.Entry(misc_frame, textvariable=self.other_subfolder_var).grid(row=1, column=1, sticky="ew")

    def _build_preview_tab(self) -> None:
        left = ttk.Frame(self.preview_tab)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="分类计划目录树").grid(row=0, column=0, sticky="w")
        self.preview_tree = ttk.Treeview(left, show="tree")
        self.preview_tree.grid(row=1, column=0, sticky="nsw")
        self.preview_tree.bind("<<TreeviewSelect>>", self._on_preview_select)

        right = ttk.Frame(self.preview_tab)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        self.preview_label = ttk.Label(right, text="分类计划详细文件")
        self.preview_label.grid(row=0, column=0, sticky="w", pady=(0, 8))

        columns = ("source_name", "target_name", "month_tag", "category_source", "confidence", "rule", "source_path")
        self.preview_detail = ttk.Treeview(right, columns=columns, show="headings")
        headings = {
            "source_name": "原文件名",
            "target_name": "归档文件名",
            "month_tag": "月份标签",
            "category_source": "分类来源",
            "confidence": "置信度",
            "rule": "命中规则",
            "source_path": "原路径",
        }
        widths = {
            "source_name": 180,
            "target_name": 220,
            "month_tag": 90,
            "category_source": 90,
            "confidence": 80,
            "rule": 180,
            "source_path": 380,
        }
        for column in columns:
            self.preview_detail.heading(column, text=headings[column])
            self.preview_detail.column(column, width=widths[column], anchor=tk.W)
        self.preview_detail.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.preview_detail.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.preview_detail.configure(yscrollcommand=scrollbar.set)

    def _refresh_all(self) -> None:
        self.misc_folder_var.set(self.ruleset.misc_folder)
        self.other_subfolder_var.set(self.ruleset.other_subfolder)
        self._refresh_project_list()
        self._refresh_special_list()
        self._refresh_preview_tree()

    def _append_chat(self, role: str, message: str) -> None:
        self.chat_history.append((role, message))
        self._append_chat_view(role, message)

    def _append_chat_view(self, role: str, message: str) -> None:
        self.chat_text.configure(state="normal")
        self.chat_text.insert(tk.END, f"{role}: {message}\n\n", self._resolve_chat_tag(role))
        self.chat_text.see(tk.END)
        self.chat_text.configure(state="disabled")

    def _resolve_chat_tag(self, role: str) -> str:
        if role == "你":
            return "role_user"
        if role == "AI":
            return "role_ai"
        return "role_system"

    def _insert_preset_prompt(self) -> None:
        prompt = PRESET_AI_PROMPTS.get(self.preset_prompt_var.get().strip(), "")
        if not prompt:
            return
        current = self.ai_prompt.get("1.0", tk.END).strip()
        merged = prompt if not current else f"{current}\n{prompt}"
        self.ai_prompt.delete("1.0", tk.END)
        self.ai_prompt.insert("1.0", merged)

    def _refresh_project_list(self) -> None:
        self.project_list.delete(0, tk.END)
        for project in self.ruleset.projects:
            marker = " [细分]" if (project.enable_subfolders or bool(project.subfolders)) else ""
            self.project_list.insert(tk.END, f"{project.folder} | {project.name}{marker}")

    def _refresh_special_list(self) -> None:
        self.special_list.delete(0, tk.END)
        self.special_list.insert(tk.END, f"零散文件目录 | {self.ruleset.misc_folder}")
        self.special_list.insert(tk.END, f"默认细分类 | {self.ruleset.other_subfolder}")
        for category in self.ruleset.special_categories:
            marker = " [细分]" if (category.enable_subfolders or bool(category.subfolders)) else ""
            self.special_list.insert(tk.END, f"{category.folder}{marker}")

    def _build_preview_cache(self) -> None:
        plan = self.planner.build_plan(self.scanned_files, self.ruleset, add_month_prefix=self.add_month_prefix)
        lookup: dict[tuple[str, str], list[PlanItem]] = defaultdict(list)
        for item in plan.items:
            lookup[(item.top_folder, item.sub_folder)].append(item)
        self.preview_lookup = dict(lookup)

    def _refresh_preview_tree(self) -> None:
        self._build_preview_cache()
        self.preview_tree.delete(*self.preview_tree.get_children())
        parents: dict[str, str] = {}
        for (top_folder, sub_folder), items in sorted(self.preview_lookup.items()):
            if top_folder not in parents:
                total = sum(len(group) for (folder, _), group in self.preview_lookup.items() if folder == top_folder)
                parents[top_folder] = self.preview_tree.insert("", tk.END, text=f"{top_folder} ({total})")
            if sub_folder:
                self.preview_tree.insert(parents[top_folder], tk.END, text=f"{sub_folder} ({len(items)})")
        if parents:
            first_parent = next(iter(parents.values()))
            self.preview_tree.selection_set(first_parent)
            self._show_preview_group(self.preview_tree.item(first_parent, "text").rsplit(" (", 1)[0], "")
        else:
            self.preview_detail.delete(*self.preview_detail.get_children())
            self.preview_label.config(text="分类计划详细文件：当前没有可预览文件")

    def _show_preview_group(self, top_folder: str, sub_folder: str) -> None:
        self.preview_detail.delete(*self.preview_detail.get_children())
        if sub_folder:
            items = self.preview_lookup.get((top_folder, sub_folder), [])
            title = f"命中文件列表：{top_folder} / {sub_folder}"
        else:
            items = [
                item
                for (folder, _), group in self.preview_lookup.items()
                if folder == top_folder
                for item in group
            ]
            title = f"命中文件列表：{top_folder}"
        self.preview_label.config(text=title)
        for item in items:
            self.preview_detail.insert(
                "",
                tk.END,
                values=(
                    item.source.name,
                    item.target_name,
                    item.source.month_tag or "-",
                    self._describe_category_source(item.category_source),
                    f"{item.confidence:.2f}",
                    item.matched_rule,
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

    def _on_preview_select(self, _event=None) -> None:
        selection = self.preview_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        parent_id = self.preview_tree.parent(item_id)
        label = self.preview_tree.item(item_id, "text").rsplit(" (", 1)[0]
        if parent_id:
            top_folder = self.preview_tree.item(parent_id, "text").rsplit(" (", 1)[0]
            self._show_preview_group(top_folder, label)
        else:
            self._show_preview_group(label, "")

    def _on_project_select(self, _event=None) -> None:
        selection = self.project_list.curselection()
        if not selection:
            return
        self.project_index = selection[0]
        project = self.ruleset.projects[self.project_index]
        self.project_name_var.set(project.name)
        self.project_folder_var.set(project.folder)
        self.project_keywords_var.set(",".join(project.keywords))
        self.enable_project_subfolders_var.set(project.enable_subfolders or bool(project.subfolders))
        self.project_subfolders_text.configure(state="normal")
        self.project_subfolders_text.delete("1.0", tk.END)
        self.project_subfolders_text.insert("1.0", _subfolders_to_text(project.subfolders))
        self._update_project_subfolder_editor_state()

    def _on_special_select(self, _event=None) -> None:
        selection = self.special_list.curselection()
        if not selection:
            return
        index = selection[0]
        if index < 2:
            return
        self.special_index = index - 2
        category = self.ruleset.special_categories[self.special_index]
        self.special_folder_var.set(category.folder)
        self.special_keywords_var.set(",".join(category.keywords))
        self.special_extensions_var.set(",".join(category.extensions))
        self.special_pattern_var.set(category.pattern)
        self.enable_special_subfolders_var.set(category.enable_subfolders or bool(category.subfolders))
        self.special_subfolders_text.configure(state="normal")
        self.special_subfolders_text.delete("1.0", tk.END)
        self.special_subfolders_text.insert("1.0", _subfolders_to_text(category.subfolders))
        self._update_special_subfolder_editor_state()

    def _add_project(self) -> None:
        index = len(self.ruleset.projects) + 1
        self.ruleset.projects.append(
            ProjectRule(name=f"新项目{index}", keywords=[], folder=f"{index:02d}_新项目{index}")
        )
        self._refresh_all()
        last = self.project_list.size() - 1
        if last >= 0:
            self.project_list.selection_clear(0, tk.END)
            self.project_list.selection_set(last)
            self._on_project_select()

    def _delete_project(self) -> None:
        if self.project_index is None:
            return
        del self.ruleset.projects[self.project_index]
        self.project_index = None
        self.project_name_var.set("")
        self.project_folder_var.set("")
        self.project_keywords_var.set("")
        self.enable_project_subfolders_var.set(False)
        self.project_subfolders_text.configure(state="normal")
        self.project_subfolders_text.delete("1.0", tk.END)
        self._update_project_subfolder_editor_state()
        self._refresh_all()

    def _save_project(self) -> None:
        if self.project_index is None:
            messagebox.showwarning("提示", "请先选择一个项目。", parent=self)
            return
        name = self.project_name_var.get().strip()
        folder = self.project_folder_var.get().strip()
        if not name or not folder:
            messagebox.showwarning("提示", "项目名称和目录名称不能为空。", parent=self)
            return
        enable_subfolders = self.enable_project_subfolders_var.get()
        subfolders = _project_subfolders_from_text(self.project_subfolders_text.get("1.0", tk.END)) if enable_subfolders else []
        self.ruleset.projects[self.project_index] = ProjectRule(
            name=name,
            folder=folder,
            keywords=_split_csv(self.project_keywords_var.get()),
            enable_subfolders=enable_subfolders,
            subfolders=subfolders,
        )
        self._apply_misc_settings()
        self._refresh_all()
        self.project_list.selection_set(self.project_index)
        self._on_project_select()

    def _add_special(self) -> None:
        self.ruleset.special_categories.append(SpecialCategoryRule(folder="98_新特殊分类"))
        self._refresh_all()
        last = self.special_list.size() - 1
        if last >= 0:
            self.special_list.selection_clear(0, tk.END)
            self.special_list.selection_set(last)
            self._on_special_select()

    def _delete_special(self) -> None:
        if self.special_index is None:
            return
        del self.ruleset.special_categories[self.special_index]
        self.special_index = None
        self.special_folder_var.set("")
        self.special_keywords_var.set("")
        self.special_extensions_var.set("")
        self.special_pattern_var.set("")
        self.enable_special_subfolders_var.set(False)
        self.special_subfolders_text.configure(state="normal")
        self.special_subfolders_text.delete("1.0", tk.END)
        self._update_special_subfolder_editor_state()
        self._refresh_all()

    def _save_special(self) -> None:
        if self.special_index is None:
            messagebox.showwarning("提示", "请先选择一个特殊分类。", parent=self)
            return
        folder = self.special_folder_var.get().strip()
        if not folder:
            messagebox.showwarning("提示", "目录名称不能为空。", parent=self)
            return
        enable_subfolders = self.enable_special_subfolders_var.get()
        subfolders = _special_subfolders_from_text(self.special_subfolders_text.get("1.0", tk.END)) if enable_subfolders else []
        self.ruleset.special_categories[self.special_index] = SpecialCategoryRule(
            folder=folder,
            keywords=_split_csv(self.special_keywords_var.get()),
            extensions=[item.lower().strip(". ") for item in _split_csv(self.special_extensions_var.get())],
            pattern=self.special_pattern_var.get().strip(),
            enable_subfolders=enable_subfolders,
            subfolders=subfolders,
        )
        self._apply_misc_settings()
        self._refresh_all()
        self.special_list.selection_set(self.special_index + 2)
        self._on_special_select()

    def _apply_misc_settings(self) -> None:
        self.ruleset.misc_folder = self.misc_folder_var.get().strip() or "90_零散文件"
        self.ruleset.other_subfolder = self.other_subfolder_var.get().strip() or "其他文件"

    def _update_project_subfolder_editor_state(self) -> None:
        if self.enable_project_subfolders_var.get():
            self.project_subfolders_text.configure(state="normal", background="#ffffff", foreground="#000000")
            return
        self.project_subfolders_text.configure(state="normal")
        self.project_subfolders_text.delete("1.0", tk.END)
        self.project_subfolders_text.configure(state="disabled", background="#f3f3f3", foreground="#666666")

    def _update_special_subfolder_editor_state(self) -> None:
        if self.enable_special_subfolders_var.get():
            self.special_subfolders_text.configure(state="normal", background="#ffffff", foreground="#000000")
            return
        self.special_subfolders_text.configure(state="normal")
        self.special_subfolders_text.delete("1.0", tk.END)
        self.special_subfolders_text.configure(state="disabled", background="#f3f3f3", foreground="#666666")

    def _use_ai(self) -> None:
        if self.ai_running:
            self._append_chat_view("系统", "AI 仍在处理中，请稍候。")
            return

        prompt_text = self.ai_prompt.get("1.0", tk.END).strip() or "请基于当前文件样本和已有规则，生成一版更合理的项目分类与特殊分类结构。"
        self._apply_misc_settings()
        reset_existing_results = self.ai_button.cget("text") == "使用AI生成建议"

        self.ai_running = True
        self.ai_button.state(["disabled"])
        self.status_var.set("正在请求 AI 生成建议，请稍候…")

        current_rules = deepcopy(self.ruleset)
        scanned_paths = [item.relative_path for item in self.scanned_files]
        self._append_chat("你", prompt_text)
        if reset_existing_results:
            self._append_chat_view("系统", "本轮会先清空上一次或示例项目结果，再按当前文件样本重新生成分类建议。")
        self._append_chat_view("系统", "已发起 API 请求，等待模型返回结果…")

        def worker() -> None:
            try:
                suggested = self.ai_service.suggest_rules(
                    scanned_paths=scanned_paths,
                    existing_rules=current_rules,
                    user_request=prompt_text,
                    conversation_history=self.chat_history,
                    reset_existing_results=reset_existing_results,
                )
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda exc=exc: self._on_ai_failed(exc))
                return
            self.after(0, lambda suggested=suggested: self._on_ai_success(suggested))

        threading.Thread(target=worker, daemon=True).start()

    def _on_ai_success(self, suggested: Ruleset) -> None:
        self.ai_running = False
        self.ruleset = suggested
        self._refresh_all()
        self.status_var.set("AI 建议已载入。你可以继续手动调整后再保存。")
        self.ai_prompt.delete("1.0", tk.END)
        self._append_chat(
            "AI",
            f"规则结构已更新，当前共有 {len(self.ruleset.projects)} 个项目规则，{len(self.ruleset.special_categories)} 个特殊分类。",
        )
        self.ai_button.configure(text="继续让AI调整")
        self.ai_button.state(["!disabled"])

    def _on_ai_failed(self, exc: Exception) -> None:
        self.ai_running = False
        message = str(exc) if isinstance(exc, AIRulesError) else f"AI 请求失败：{exc}"
        self.status_var.set(message)
        self._append_chat("系统", message)
        messagebox.showerror("AI 规则生成失败", message, parent=self)
        self.ai_button.state(["!disabled"])

    def _ensure_api_config(self) -> None:
        path = self.ai_service.ensure_api_config()
        message = f"API 配置文件已就绪：{path}"
        self.status_var.set(message)
        self._append_chat("系统", message)
        messagebox.showinfo("API 配置", f"请检查并填写：\n{path}", parent=self)

    def _save_rules(self) -> None:
        if self.project_index is not None:
            self._save_project()
        if self.special_index is not None:
            self._save_special()
        self._apply_misc_settings()
        self.on_save(self.ruleset)
        self.status_var.set("规则已保存，预览也已同步更新。")
        self._append_chat("系统", "规则已保存，当前预览已同步刷新。")
        self._refresh_preview_tree()
