"""devnotes GUI — a small dark-themed desktop app on top of the same
SQLite backend the CLI uses. Every note you take in one shows up in
the other immediately (same ~/.devnotes/notes.db, or the same
$DEVNOTES_HOME).

Run with: devnotes-gui   (after `pip install -e .`)
      or: python -m devnotes.gui
"""
from __future__ import annotations

import json
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import calendar_utils as cal
from . import db, git_utils, highlight
from .paths import backup_dir
from .templates import get_template, template_names

PALETTE = highlight.PALETTE


def pick_mono_font(root) -> str:
    candidates = [
        "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas",
        "Menlo", "SF Mono", "DejaVu Sans Mono", "Courier New",
    ]
    available = set(tkfont.families(root))
    for c in candidates:
        if c in available:
            return c
    return "Courier"


class DevNotesGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        db.init_db()

        self.title("devnotes")
        self.geometry("1180x720")
        self.minsize(820, 480)
        self.configure(bg=PALETTE["bg"])

        self.mono_font = pick_mono_font(self)
        self.current_note_id: int | None = None
        self.dirty = False
        self._suppress_dirty = False
        self._highlight_job = None
        self._search_job = None
        self.repo, self.branch = git_utils.get_context()

        self._build_style()
        self._build_menu()
        self._build_layout()
        self._bind_shortcuts()

        self.refresh_filters()
        self.refresh_list()
        self._new_note(confirm=False)
        self._update_git_status()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # styling
    # ------------------------------------------------------------------ #
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=PALETTE["bg"])
        style.configure("Panel.TFrame", background=PALETTE["panel"])
        style.configure(
            "TLabel", background=PALETTE["bg"], foreground=PALETTE["fg"], font=("", 10)
        )
        style.configure(
            "Dim.TLabel", background=PALETTE["bg"], foreground=PALETTE["fg_dim"], font=("", 9)
        )
        style.configure(
            "Status.TLabel", background=PALETTE["panel"], foreground=PALETTE["fg_dim"], font=("", 9)
        )
        style.configure(
            "TButton",
            background=PALETTE["bg_alt"],
            foreground=PALETTE["fg"],
            borderwidth=0,
            focusthickness=0,
            padding=6,
        )
        style.map(
            "TButton",
            background=[("active", PALETTE["select"]), ("pressed", PALETTE["select"])],
        )
        style.configure(
            "Accent.TButton", background=PALETTE["accent"], foreground="#04263d", padding=6
        )
        style.map("Accent.TButton", background=[("active", "#6fd0ff")])
        style.configure(
            "Danger.TButton", background=PALETTE["bg_alt"], foreground=PALETTE["danger"], padding=6
        )
        style.configure(
            "TEntry",
            fieldbackground=PALETTE["bg_alt"],
            foreground=PALETTE["fg"],
            insertcolor=PALETTE["fg"],
            borderwidth=0,
            padding=5,
        )
        style.configure(
            "TCombobox",
            fieldbackground=PALETTE["bg_alt"],
            background=PALETTE["bg_alt"],
            foreground=PALETTE["fg"],
            arrowcolor=PALETTE["fg"],
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", PALETTE["bg_alt"]), ("disabled", PALETTE["bg_alt"])],
            foreground=[("readonly", PALETTE["fg"]), ("disabled", PALETTE["fg_dim"])],
            background=[("readonly", PALETTE["bg_alt"])],
            selectbackground=[("readonly", PALETTE["bg_alt"])],
            selectforeground=[("readonly", PALETTE["fg"])],
        )
        self.option_add("*TCombobox*Listbox.background", PALETTE["bg_alt"])
        self.option_add("*TCombobox*Listbox.foreground", PALETTE["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", PALETTE["select"])
        style.configure(
            "Treeview",
            background=PALETTE["panel"],
            fieldbackground=PALETTE["panel"],
            foreground=PALETTE["fg"],
            borderwidth=0,
            rowheight=26,
        )
        style.map(
            "Treeview",
            background=[("selected", PALETTE["select"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background=PALETTE["bg_alt"],
            foreground=PALETTE["fg_dim"],
            borderwidth=0,
            relief="flat",
        )
        style.configure("TCheckbutton", background=PALETTE["bg"], foreground=PALETTE["fg"])
        style.map("TCheckbutton", background=[("active", PALETTE["bg"])])
        style.configure("TPanedwindow", background=PALETTE["border"])

    # ------------------------------------------------------------------ #
    # menu
    # ------------------------------------------------------------------ #
    def _build_menu(self) -> None:
        menubar = tk.Menu(self)

        filem = tk.Menu(menubar, tearoff=0)
        filem.add_command(label="New Note", accelerator="Ctrl+N", command=self._new_note)
        filem.add_command(label="Save", accelerator="Ctrl+S", command=self.save_note)
        filem.add_separator()
        filem.add_command(label="Export All (JSON)…", command=self.export_json)
        filem.add_command(label="Import (JSON)…", command=self.import_json)
        filem.add_command(label="Export Note as Markdown…", command=self.export_markdown)
        filem.add_separator()
        filem.add_command(label="Quit", accelerator="Ctrl+Q", command=self._on_close)
        menubar.add_cascade(label="File", menu=filem)

        notem = tk.Menu(menubar, tearoff=0)
        notem.add_command(label="Toggle Pin", accelerator="Ctrl+P", command=self.toggle_pin)
        notem.add_command(label="Toggle Archive", accelerator="Ctrl+Shift+A", command=self.toggle_archive)
        notem.add_command(label="Delete…", accelerator="Ctrl+Backspace", command=self.delete_note)
        menubar.add_cascade(label="Note", menu=notem)

        calm = tk.Menu(menubar, tearoff=0)
        calm.add_command(label="Open 45-Day Planner…", accelerator="Ctrl+Shift+C", command=self.open_calendar_dialog)
        calm.add_command(label="Today's Plan", accelerator="Ctrl+T", command=self.open_today)
        menubar.add_cascade(label="Calendar", menu=calm)

        insertm = tk.Menu(menubar, tearoff=0)
        for name in template_names():
            insertm.add_command(
                label=name.capitalize(), command=lambda n=name: self.insert_template(n)
            )
        menubar.add_cascade(label="Insert Template", menu=insertm)

        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        helpm.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=helpm)

        self.config(menu=menubar)

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(paned, style="Panel.TFrame", padding=8)
        right = ttk.Frame(paned, padding=(12, 8, 12, 8))
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        self._build_sidebar(left)
        self._build_editor(right)
        self._build_statusbar()

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        top = ttk.Frame(parent, style="Panel.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        top.columnconfigure(0, weight=1)
        top.columnconfigure(1, weight=0)

        ttk.Button(top, text="+ New Note", style="Accent.TButton", command=self._new_note).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(top, text="Cal", width=4, command=self.open_calendar_dialog).grid(
            row=0, column=1, sticky="ew", padx=(4, 0)
        )

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._schedule_search())
        search_entry = ttk.Entry(parent, textvariable=self.search_var)
        search_entry.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        search_entry.insert(0, "")
        self._search_entry = search_entry
        self._add_placeholder(search_entry, "Search notes…")

        filters = ttk.Frame(parent, style="Panel.TFrame")
        filters.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        filters.columnconfigure(0, weight=1)
        filters.columnconfigure(1, weight=1)

        self.project_filter = tk.StringVar(value="All Projects")
        self.project_combo = ttk.Combobox(
            filters, textvariable=self.project_filter, state="readonly"
        )
        self.project_combo.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.project_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())

        self.tag_filter = tk.StringVar(value="All Tags")
        self.tag_combo = ttk.Combobox(filters, textvariable=self.tag_filter, state="readonly")
        self.tag_combo.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.tag_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_list())

        self.show_archived_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            parent,
            text="Show archived",
            variable=self.show_archived_var,
            command=self.refresh_list,
        ).grid(row=3, column=0, sticky="w", pady=(0, 6))

        columns = ("title", "meta")
        self.tree = ttk.Treeview(
            parent, columns=columns, show="tree headings", selectmode="browse"
        )
        self.tree.grid(row=4, column=0, sticky="nsew")
        parent.rowconfigure(4, weight=1)
        self.tree.heading("#0", text="")
        self.tree.column("#0", width=28, stretch=False, anchor="center")
        self.tree.heading("title", text="Note")
        self.tree.column("title", width=170)
        self.tree.heading("meta", text="Updated")
        self.tree.column("meta", width=90, anchor="e")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_note)

        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=4, column=1, sticky="ns")

    def _add_placeholder(self, entry: ttk.Entry, text: str) -> None:
        entry.insert(0, text)

        def on_focus_in(_e):
            if entry.get() == text:
                entry.delete(0, tk.END)

        def on_focus_out(_e):
            if not entry.get():
                entry.insert(0, text)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        self._search_placeholder = text

    def _build_editor(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(3, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Save", command=self.save_note).pack(side=tk.LEFT)
        self.pin_btn = ttk.Button(toolbar, text="★ Pin", command=self.toggle_pin)
        self.pin_btn.pack(side=tk.LEFT, padx=4)
        self.archive_btn = ttk.Button(toolbar, text="Archive", command=self.toggle_archive)
        self.archive_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="Delete", style="Danger.TButton", command=self.delete_note).pack(
            side=tk.LEFT, padx=4
        )
        self.dirty_label = ttk.Label(toolbar, text="", style="Dim.TLabel")
        self.dirty_label.pack(side=tk.RIGHT)

        fields = ttk.Frame(parent)
        fields.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        fields.columnconfigure(1, weight=1)
        fields.columnconfigure(3, weight=1)

        ttk.Label(fields, text="Title").grid(row=0, column=0, sticky="w")
        self.title_var = tk.StringVar()
        self.title_var.trace_add("write", self._on_field_change)
        title_entry = ttk.Entry(fields, textvariable=self.title_var, font=("", 13, "bold"))
        title_entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 6))
        self.title_entry = title_entry

        ttk.Label(fields, text="Tags (comma-separated)").grid(row=2, column=0, sticky="w")
        ttk.Label(fields, text="Project").grid(row=2, column=2, sticky="w")
        self.tags_var = tk.StringVar()
        self.tags_var.trace_add("write", self._on_field_change)
        ttk.Entry(fields, textvariable=self.tags_var).grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=(0, 6)
        )
        self.project_var = tk.StringVar()
        self.project_var.trace_add("write", self._on_field_change)
        ttk.Entry(fields, textvariable=self.project_var).grid(
            row=3, column=2, columnspan=2, sticky="ew"
        )

        body_frame = ttk.Frame(parent)
        body_frame.grid(row=3, column=0, sticky="nsew")
        body_frame.rowconfigure(0, weight=1)
        body_frame.columnconfigure(0, weight=1)

        self.body_text = tk.Text(
            body_frame,
            wrap="word",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            bg=PALETTE["bg_alt"],
            fg=PALETTE["fg"],
            insertbackground=PALETTE["fg"],
            selectbackground=PALETTE["select"],
            relief="flat",
            font=(self.mono_font, 11),
            padx=10,
            pady=10,
        )
        self.body_text.grid(row=0, column=0, sticky="nsew")
        body_scroll = ttk.Scrollbar(body_frame, orient="vertical", command=self.body_text.yview)
        self.body_text.configure(yscrollcommand=body_scroll.set)
        body_scroll.grid(row=0, column=1, sticky="ns")

        highlight.configure_tags(self.body_text)
        self.body_text.bind("<<Modified>>", self._on_body_modified)

        meta_row = ttk.Frame(parent)
        meta_row.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.meta_label = ttk.Label(meta_row, text="", style="Dim.TLabel")
        self.meta_label.pack(side=tk.LEFT)
        self.count_label = ttk.Label(meta_row, text="", style="Dim.TLabel")
        self.count_label.pack(side=tk.RIGHT)

    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, style="Panel.TFrame", padding=(10, 4))
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        self.git_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.git_label.pack(side=tk.LEFT)
        self.list_count_label = ttk.Label(bar, text="", style="Status.TLabel")
        self.list_count_label.pack(side=tk.RIGHT)

    def _update_git_status(self) -> None:
        if self.repo:
            self.git_label.configure(text=f"{self.repo}  ·  branch: {self.branch or '—'}")
        else:
            self.git_label.configure(text="no git repo detected in current directory")

    # ------------------------------------------------------------------ #
    # shortcuts
    # ------------------------------------------------------------------ #
    def _bind_shortcuts(self) -> None:
        self.bind_all("<Control-n>", lambda e: self._new_note())
        self.bind_all("<Control-s>", lambda e: self.save_note())
        self.bind_all("<Control-Return>", lambda e: self.save_note())
        self.bind_all("<Control-f>", lambda e: self._focus_search())
        self.bind_all("<Control-p>", lambda e: self.toggle_pin())
        self.bind_all("<Control-Shift-A>", lambda e: self.toggle_archive())
        self.bind_all("<Control-Shift-a>", lambda e: self.toggle_archive())
        self.bind_all("<Control-BackSpace>", lambda e: self.delete_note())
        self.bind_all("<Control-q>", lambda e: self._on_close())
        self.bind_all("<Control-Shift-C>", lambda e: self.open_calendar_dialog())
        self.bind_all("<Control-Shift-c>", lambda e: self.open_calendar_dialog())
        self.bind_all("<Control-t>", lambda e: self.open_today())

    def _focus_search(self) -> None:
        self._search_entry.focus_set()
        if self._search_entry.get() == self._search_placeholder:
            self._search_entry.delete(0, tk.END)

    # ------------------------------------------------------------------ #
    # list / filters
    # ------------------------------------------------------------------ #
    def refresh_filters(self) -> None:
        projects = ["All Projects"] + [p for p, _ in db.all_projects_with_counts()]
        tags = ["All Tags"] + [t for t, _ in db.all_tags_with_counts()]
        cur_p, cur_t = self.project_filter.get(), self.tag_filter.get()
        self.project_combo["values"] = projects
        self.tag_combo["values"] = tags
        if cur_p not in projects:
            self.project_filter.set("All Projects")
        if cur_t not in tags:
            self.tag_filter.set("All Tags")

    def _schedule_search(self) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(250, self.refresh_list)

    def refresh_list(self) -> None:
        self.refresh_filters()
        project = self.project_filter.get()
        project = None if project == "All Projects" else project
        tag = self.tag_filter.get()
        tag = None if tag == "All Tags" else tag
        query = self.search_var.get().strip()
        if query == getattr(self, "_search_placeholder", None):
            query = ""

        notes = db.list_notes(
            project=project,
            tag=tag,
            query=query or None,
            include_archived=self.show_archived_var.get(),
        )

        self.tree.delete(*self.tree.get_children())
        for n in notes:
            pin = "★" if n.pinned else ""
            when = n.updated_at.split("T")[0]
            label = n.title + (" (archived)" if n.archived else "")
            self.tree.insert("", tk.END, iid=str(n.id), text=pin, values=(label, when))

        self.list_count_label.configure(text=f"{len(notes)} note(s)")
        if self.current_note_id is not None:
            iid = str(self.current_note_id)
            if self.tree.exists(iid):
                self.tree.selection_set(iid)

    def _on_select_note(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        note_id = int(selection[0])
        if note_id == self.current_note_id:
            return
        if not self._confirm_discard_if_dirty():
            # revert selection back to the current note
            if self.current_note_id is not None:
                self.tree.selection_set(str(self.current_note_id))
            return
        self._load_note(note_id)

    # ------------------------------------------------------------------ #
    # editor state
    # ------------------------------------------------------------------ #
    def _load_note(self, note_id: int) -> None:
        note = db.get_note(note_id)
        if not note:
            return
        self.current_note_id = note.id
        self._suppress_dirty = True
        self.title_var.set(note.title)
        self.tags_var.set(", ".join(note.tags))
        self.project_var.set(note.project or "")
        self.body_text.delete("1.0", tk.END)
        self.body_text.insert("1.0", note.body)
        self.body_text.edit_modified(False)
        self.body_text.edit_reset()
        self._suppress_dirty = False
        self._set_dirty(False)
        self._refresh_editor_chrome(note)
        self.do_highlight()

    def _new_note(self, confirm: bool = True) -> None:
        if confirm and not self._confirm_discard_if_dirty():
            return
        self.current_note_id = None
        self._suppress_dirty = True
        self.title_var.set("")
        self.tags_var.set(f"branch:{self.branch}" if self.branch else "")
        self.project_var.set(self.repo or "")
        self.body_text.delete("1.0", tk.END)
        self.body_text.edit_modified(False)
        self.body_text.edit_reset()
        self._suppress_dirty = False
        self._set_dirty(False)
        self._refresh_editor_chrome(None)
        self.title_entry.focus_set()

    def _refresh_editor_chrome(self, note) -> None:
        if note is None:
            self.meta_label.configure(text="New, unsaved note")
            self.pin_btn.configure(text="★ Pin")
            self.archive_btn.configure(text="Archive")
        else:
            self.meta_label.configure(
                text=f"#{note.id} · created {note.created_at.replace('T', ' ')}"
            )
            self.pin_btn.configure(text="★ Unpin" if note.pinned else "★ Pin")
            self.archive_btn.configure(text="Unarchive" if note.archived else "Archive")
        self._update_word_count()

    def _on_field_change(self, *_args) -> None:
        if not self._suppress_dirty:
            self._set_dirty(True)

    def _on_body_modified(self, _event=None) -> None:
        if self.body_text.edit_modified():
            if not self._suppress_dirty:
                self._set_dirty(True)
            self._update_word_count()
            self._schedule_highlight()
            self.body_text.edit_modified(False)

    def _update_word_count(self) -> None:
        content = self.body_text.get("1.0", "end-1c")
        words = len(content.split())
        chars = len(content)
        self.count_label.configure(text=f"{words} words · {chars} chars")

    def _schedule_highlight(self) -> None:
        if self._highlight_job:
            self.after_cancel(self._highlight_job)
        self._highlight_job = self.after(250, self.do_highlight)

    def do_highlight(self) -> None:
        highlight.highlight(self.body_text)

    def _set_dirty(self, value: bool) -> None:
        self.dirty = value
        self.dirty_label.configure(text="● unsaved changes" if value else "")

    def _confirm_discard_if_dirty(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes", "Save changes to the current note before switching?"
        )
        if answer is None:
            return False
        if answer:
            self.save_note()
        return True

    # ------------------------------------------------------------------ #
    # actions
    # ------------------------------------------------------------------ #
    def save_note(self) -> None:
        title = self.title_var.get().strip()
        if not title:
            title = "Untitled note"
            self.title_var.set(title)
        body = self.body_text.get("1.0", "end-1c")
        tags = [t.strip().lstrip("#") for t in self.tags_var.get().split(",") if t.strip()]
        project = self.project_var.get().strip() or None

        if self.current_note_id is None:
            note_id = db.add_note(
                title=title, body=body, tags=tags, project=project, branch=self.branch
            )
            self.current_note_id = note_id
        else:
            db.update_note(self.current_note_id, title=title, body=body, tags=tags)
            with db.connect() as conn:
                conn.execute(
                    "UPDATE notes SET project = ? WHERE id = ?", (project, self.current_note_id)
                )

        self._set_dirty(False)
        self.refresh_list()
        note = db.get_note(self.current_note_id)
        self._refresh_editor_chrome(note)

    def toggle_pin(self) -> None:
        if self.current_note_id is None:
            messagebox.showinfo("devnotes", "Save the note first.")
            return
        note = db.get_note(self.current_note_id)
        db.set_flag(self.current_note_id, "pinned", not note.pinned)
        self.refresh_list()
        self._refresh_editor_chrome(db.get_note(self.current_note_id))

    def toggle_archive(self) -> None:
        if self.current_note_id is None:
            messagebox.showinfo("devnotes", "Save the note first.")
            return
        note = db.get_note(self.current_note_id)
        db.set_flag(self.current_note_id, "archived", not note.archived)
        self.refresh_list()
        self._refresh_editor_chrome(db.get_note(self.current_note_id))

    def delete_note(self) -> None:
        if self.current_note_id is None:
            return
        title = self.title_var.get() or "this note"
        if not messagebox.askyesno("Delete note", f"Permanently delete '{title}'?"):
            return
        db.delete_note(self.current_note_id)
        self._new_note(confirm=False)
        self.refresh_list()

    def insert_template(self, name: str) -> None:
        text = get_template(name)
        self.body_text.insert(tk.INSERT, text)
        self._schedule_highlight()
        self._set_dirty(True)

    # ------------------------------------------------------------------ #
    # calendar pipeline: 45-day forward planner -> one note per day
    # ------------------------------------------------------------------ #
    def open_today(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self._open_calendar_date(date.today())

    def _open_calendar_date(self, target_date: date) -> None:
        iso = target_date.isoformat()
        weekday = target_date.strftime("%A")
        title = f"Plan: {iso} ({weekday})"
        note, created = db.get_or_create_daily_note(iso, title=title, project=self.repo)
        # Load first, then refresh the list — refresh_list() reselects
        # `current_note_id` in the tree, which queues a <<TreeviewSelect>>
        # event; loading first ensures that event reselects the *new*
        # note instead of reverting back to whatever was open before.
        self._load_note(note.id)
        self.refresh_list()
        if created:
            self.body_text.focus_set()

    def open_calendar_dialog(self) -> None:
        if not self._confirm_discard_if_dirty():
            return

        window_days = cal.forward_window()
        grid = cal.weeks_grid(window_days)
        labels = cal.month_headers(grid)
        counts = db.daily_note_dates()
        today = date.today()

        win = tk.Toplevel(self)
        win.title("45-Day Planner")
        win.configure(bg=PALETTE["bg"])
        win.transient(self)
        win.resizable(False, False)

        header = ttk.Frame(win, padding=(12, 10, 12, 4))
        header.pack(fill=tk.X)
        ttk.Label(header, text="Next 45 Days", font=("", 13, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text="click a day to open or create its note", style="Dim.TLabel").pack(
            side=tk.RIGHT
        )

        grid_frame = ttk.Frame(win, padding=(12, 4, 12, 4))
        grid_frame.pack()

        for col, wd in enumerate(cal.WEEKDAY_LABELS):
            ttk.Label(grid_frame, text=wd, style="Dim.TLabel").grid(
                row=0, column=col + 1, padx=2, pady=(0, 4)
            )

        for r, (week_row, month_label) in enumerate(zip(grid, labels), start=1):
            ttk.Label(grid_frame, text=month_label or "", style="Dim.TLabel", width=7).grid(
                row=r, column=0, sticky="w", padx=(0, 6)
            )
            for col, cell in enumerate(week_row):
                if cell is None:
                    ttk.Label(grid_frame, text="", width=4).grid(row=r, column=col + 1)
                    continue
                d = cell.day
                has_note = counts.get(d.isoformat(), 0) > 0
                if d == today:
                    bg, fg, active = PALETTE["accent"], "#04263d", "#6fd0ff"
                elif has_note:
                    bg, fg, active = PALETTE["success"], "#04260f", "#a8e6b8"
                else:
                    bg, fg, active = PALETTE["bg_alt"], PALETTE["fg"], PALETTE["select"]
                btn = tk.Button(
                    grid_frame,
                    text=str(d.day),
                    width=4,
                    bg=bg,
                    fg=fg,
                    relief="flat",
                    activebackground=active,
                    borderwidth=0,
                    command=lambda dd=d: (win.destroy(), self._open_calendar_date(dd)),
                )
                btn.grid(row=r, column=col + 1, padx=2, pady=2)

        legend = ttk.Frame(win, padding=(12, 4, 12, 12))
        legend.pack(fill=tk.X)
        ttk.Label(legend, text="■", foreground=PALETTE["success"]).pack(side=tk.LEFT)
        ttk.Label(legend, text="has a note   ", style="Dim.TLabel").pack(side=tk.LEFT)
        ttk.Label(legend, text="■", foreground=PALETTE["accent"]).pack(side=tk.LEFT)
        ttk.Label(legend, text="today", style="Dim.TLabel").pack(side=tk.LEFT)

        win.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_y() + (self.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    # ------------------------------------------------------------------ #
    # import / export
    # ------------------------------------------------------------------ #
    def export_json(self) -> None:
        notes = db.list_notes(include_archived=True)
        payload = [
            {
                "id": n.id, "title": n.title, "body": n.body, "project": n.project,
                "branch": n.branch, "pinned": n.pinned, "archived": n.archived,
                "tags": n.tags, "created_at": n.created_at, "updated_at": n.updated_at,
            }
            for n in notes
        ]
        default = str(backup_dir() / f"devnotes-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        path = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile=Path(default).name, filetypes=[("JSON", "*.json")]
        )
        if not path:
            return
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        messagebox.showinfo("devnotes", f"Exported {len(payload)} notes to {path}")

    def import_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data:
            db.add_note(
                title=item.get("title", "(untitled)"),
                body=item.get("body", ""),
                tags=item.get("tags", []),
                project=item.get("project"),
                branch=item.get("branch"),
                pinned=item.get("pinned", False),
            )
        self.refresh_list()
        messagebox.showinfo("devnotes", f"Imported {len(data)} notes.")

    def export_markdown(self) -> None:
        if self.current_note_id is None:
            messagebox.showinfo("devnotes", "Save the note first.")
            return
        note = db.get_note(self.current_note_id)
        lines = [f"# {note.title}", ""]
        if note.tags:
            lines.append(" ".join(f"#{t}" for t in note.tags))
            lines.append("")
        lines.append(note.body)
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=f"note-{note.id}.md",
            filetypes=[("Markdown", "*.md")],
        )
        if not path:
            return
        Path(path).write_text("\n".join(lines), encoding="utf-8")
        messagebox.showinfo("devnotes", f"Exported to {path}")

    # ------------------------------------------------------------------ #
    # help / misc
    # ------------------------------------------------------------------ #
    def _show_shortcuts(self) -> None:
        messagebox.showinfo(
            "Keyboard Shortcuts",
            "Ctrl+N        New note\n"
            "Ctrl+S        Save\n"
            "Ctrl+Enter    Save\n"
            "Ctrl+F        Focus search\n"
            "Ctrl+P        Toggle pin\n"
            "Ctrl+Shift+A  Toggle archive\n"
            "Ctrl+Backspace  Delete note\n"
            "Ctrl+Shift+C  Open 45-day planner\n"
            "Ctrl+T        Today's plan\n"
            "Ctrl+Q        Quit",
        )

    def _show_about(self) -> None:
        pyg = "with Pygments syntax highlighting" if highlight.HAS_PYGMENTS else "without Pygments (plain code blocks)"
        messagebox.showinfo("About devnotes", f"devnotes GUI\nRunning {pyg}.\nData: same SQLite DB as the devnotes CLI.")

    def _on_close(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        self.destroy()


def main() -> None:
    app = DevNotesGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
