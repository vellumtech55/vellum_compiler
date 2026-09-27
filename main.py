"""
Directory Creator
------------------
GUI tool to bulk-create folder/file structures from a shorthand syntax.

Syntax:
  /   nested folder (folder inside folder)
  ,   files inside the folder immediately before the comma
      (comma-separated list -> files, not a subfolder)
  |   sibling folders/trees, all rooted at the Start Directory
  (newlines also separate top-level entries, same as |)

Examples:
  project/src/main.py,utils.py|project/docs/readme.md,notes.md|project/tests

  -> project/
       src/
         main.py
         utils.py
       docs/
         readme.md
         notes.md
       tests/

To create a single standalone file (no siblings), give it a trailing comma:
  project/readme.md,
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def parse_entries(text):
    entries = []
    for line in text.splitlines():
        for part in line.split("|"):
            part = part.strip()
            if part:
                entries.append(part)
    return entries


def build_tree(entries):
    """Merge all entries into one nested dict tree.
    Folders are keys mapping to subtree dicts.
    Files live under the special key '__files__' (a list) on their parent node.
    """
    tree = {}
    for entry in entries:
        segments = [s.strip() for s in entry.split("/") if s.strip()]
        if not segments:
            continue
        node = tree
        for seg in segments[:-1]:
            node = node.setdefault(seg, {})
        last = segments[-1]
        if "," in last:
            files = [f.strip() for f in last.split(",") if f.strip()]
            bucket = node.setdefault("__files__", [])
            for f in files:
                if f not in bucket:
                    bucket.append(f)
        else:
            node.setdefault(last, {})
    return tree


def render_tree(tree, prefix=""):
    lines = []
    folders = sorted(k for k in tree if k != "__files__")
    files = sorted(tree.get("__files__", []))
    for f in folders:
        lines.append(f"{prefix}\U0001F4C1 {f}/")
        lines.extend(render_tree(tree[f], prefix + "    "))
    for fl in files:
        lines.append(f"{prefix}\U0001F4C4 {fl}")
    return lines


def create_from_tree(base, tree, log):
    os.makedirs(base, exist_ok=True)
    log.append(f"dir  {base}")
    for key, val in tree.items():
        if key == "__files__":
            for f in val:
                fpath = os.path.join(base, f)
                open(fpath, "a").close()
                log.append(f"file {fpath}")
        else:
            create_from_tree(os.path.join(base, key), val, log)


class DirectoryCreatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Directory Creator")
        self.geometry("760x600")
        self.minsize(600, 480)
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 8, "pady": 6}

        # Start directory row
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text="Start Directory:").pack(side="left")
        self.start_var = tk.StringVar(value=os.getcwd())
        ttk.Entry(top, textvariable=self.start_var).pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(top, text="Browse...", command=self._browse).pack(side="left")

        # Pattern input
        ttk.Label(
            self,
            text="Structure Pattern  (/ nested folders, comma = files, | sibling trees):",
        ).pack(anchor="w", padx=8)
        self.pattern_text = tk.Text(self, height=8, wrap="none")
        self.pattern_text.pack(fill="both", expand=False, padx=8, pady=(0, 6))
        self.pattern_text.insert(
            "1.0",
            "project/src/main.py,utils.py|project/docs/readme.md,notes.md|project/tests",
        )

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Preview", command=self._preview).pack(side="left")
        ttk.Button(btns, text="Create", command=self._create).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear Log", command=self._clear_log).pack(side="left")

        # Output/log
        ttk.Label(self, text="Preview / Log:").pack(anchor="w", padx=8)
        out_frame = ttk.Frame(self)
        out_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.output = tk.Text(out_frame, wrap="none", state="disabled")
        yscroll = ttk.Scrollbar(out_frame, orient="vertical", command=self.output.yview)
        xscroll = ttk.Scrollbar(out_frame, orient="horizontal", command=self.output.xview)
        self.output.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.output.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        out_frame.rowconfigure(0, weight=1)
        out_frame.columnconfigure(0, weight=1)

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.start_var.get() or os.getcwd())
        if d:
            self.start_var.set(d)

    def _write_log(self, lines, clear=True):
        self.output.configure(state="normal")
        if clear:
            self.output.delete("1.0", "end")
        self.output.insert("end", "\n".join(lines) + "\n")
        self.output.configure(state="disabled")

    def _clear_log(self):
        self._write_log([], clear=True)

    def _get_tree(self):
        pattern = self.pattern_text.get("1.0", "end")
        entries = parse_entries(pattern)
        if not entries:
            messagebox.showwarning("No pattern", "Enter a structure pattern first.")
            return None
        return build_tree(entries)

    def _preview(self):
        tree = self._get_tree()
        if tree is None:
            return
        base = self.start_var.get().strip() or "."
        lines = [f"{base}/"] + render_tree(tree, "    ")
        self._write_log(lines)

    def _create(self):
        tree = self._get_tree()
        if tree is None:
            return
        base = self.start_var.get().strip()
        if not base:
            messagebox.showwarning("No start directory", "Choose a start directory first.")
            return
        try:
            log = []
            create_from_tree(base, tree, log)
            self._write_log(log + ["", "Done."])
            messagebox.showinfo("Directory Creator", "Structure created successfully.")
        except Exception as e:
            self._write_log([f"ERROR: {e}"])
            messagebox.showerror("Directory Creator", f"Failed: {e}")


if __name__ == "__main__":
    app = DirectoryCreatorApp()
    app.mainloop()
