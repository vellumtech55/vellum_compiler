"""
Audio Converter Pro
Main application.

Cross-platform fixes vs. the original:
  - ffmpeg is located once at startup via utils.find_tool() (PATH +
    bundled copy + common per-OS install paths) instead of assuming
    "ffmpeg" is just callable. If it's missing, the user gets a clear,
    OS-specific message instead of every conversion silently failing.
  - The worker thread never touches Tk widgets directly. It only pushes
    events onto a thread-safe queue.Queue; the main thread drains that
    queue on a Tk `after()` timer. Calling Tk methods from a background
    thread (as the original did) is undefined behavior on some
    platforms and a common source of Windows-only crashes.
  - Conversion can be cancelled mid-run.
  - Progress reflects real per-file ffmpeg progress, not just a file
    count.
"""

import queue
import threading
import tkinter.messagebox as messagebox
from tkinter import filedialog, ttk

import customtkinter as ctk

from converter import convert_file
from queue_manager import QueueManager
from settings_manager import load_settings, save_settings
from settings_tab import SettingsTab
from utils import get_ffmpeg_path, get_ffprobe_path, install_instructions, is_supported

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#00BFFF"
BACKGROUND = "#08192D"


class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("Audio Converter Pro")
        self.geometry("1100x720")
        self.minsize(820, 560)
        self.resizable(True, True)

        self.settings = load_settings()
        self.queue = QueueManager()
        self.output_folder = ""

        self.ffmpeg_path = get_ffmpeg_path()
        self.ffprobe_path = get_ffprobe_path()

        self.ui_events = queue.Queue()
        self.cancel_event = threading.Event()
        self.worker_thread = None

        self._build_ui()
        self.after(100, self._drain_ui_events)

        if not self.ffmpeg_path:
            self.after(300, self._warn_missing_ffmpeg)

    # ----------------------------
    # UI
    # ----------------------------
    def _build_ui(self):
        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=12, pady=12)

        self._build_converter_tab(tabs.add("Converter"))

        settings_frame = tabs.add("Settings")
        self.settings_tab = SettingsTab(
            settings_frame, self.settings, on_save=self._save_settings, accent_color=ACCENT
        )
        self.settings_tab.pack(fill="both", expand=True)

    def _build_converter_tab(self, parent):
        toolbar = ctk.CTkFrame(parent, fg_color=BACKGROUND)
        toolbar.pack(fill="x", padx=8, pady=8)

        self.add_btn = ctk.CTkButton(toolbar, text="Add Files", fg_color=ACCENT, width=120, command=self._add_files)
        self.output_btn = ctk.CTkButton(toolbar, text="Output Folder", fg_color=ACCENT, width=120, command=self._select_output)
        self.convert_btn = ctk.CTkButton(toolbar, text="Convert", fg_color=ACCENT, width=120, command=self._start_conversion)
        self.clear_btn = ctk.CTkButton(toolbar, text="Clear Queue", fg_color=ACCENT, width=120, command=self._clear_queue)
        self.cancel_btn = ctk.CTkButton(
            toolbar, text="Cancel", fg_color="#B33A3A", width=100, command=self._cancel_conversion, state="disabled"
        )

        for btn in (self.add_btn, self.output_btn, self.convert_btn, self.clear_btn, self.cancel_btn):
            btn.pack(side="left", padx=4, pady=6)

        self.file_count_label = ctk.CTkLabel(toolbar, text="Queue: 0 files")
        self.file_count_label.pack(side="right", padx=16)

        self.folder_label = ctk.CTkLabel(toolbar, text="No output folder selected", text_color="gray")
        self.folder_label.pack(side="right", padx=8)

        self.queue_table = ttk.Treeview(parent, columns=("file", "status"), show="headings", height=16)
        self.queue_table.heading("file", text="File")
        self.queue_table.heading("status", text="Status")
        self.queue_table.column("file", width=820)
        self.queue_table.column("status", width=200, anchor="center")
        self.queue_table.pack(fill="both", expand=True, padx=8, pady=4)

        self.progress = ttk.Progressbar(parent, mode="determinate", maximum=1000)
        self.progress.pack(fill="x", padx=8, pady=4)

        self.log = ctk.CTkTextbox(parent, height=130, state="disabled")
        self.log.pack(fill="x", padx=8, pady=6)

    # ----------------------------
    # Actions
    # ----------------------------
    def _add_files(self):
        paths = filedialog.askopenfilenames()
        added = 0
        skipped_unsupported = 0

        for p in paths:
            if self.queue.contains(p):
                continue
            if not is_supported(p):
                skipped_unsupported += 1
                continue
            self.queue.add(p)
            self.queue_table.insert("", "end", iid=p, values=(p, "Waiting"))
            added += 1

        self._update_count()

        if added:
            self._log(f"Added {added} file(s).")
        if skipped_unsupported:
            self._log(f"Skipped {skipped_unsupported} unsupported file(s).")

    def _select_output(self):
        folder = filedialog.askdirectory()
        if folder:
            self.output_folder = folder
            self.folder_label.configure(text=folder, text_color="white")
            self._log(f"Output → {folder}")

    def _clear_queue(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self._log("Can't clear the queue while a conversion is running.")
            return
        self.queue.clear()
        for row in self.queue_table.get_children():
            self.queue_table.delete(row)
        self.progress["value"] = 0
        self._update_count()

    def _save_settings(self, values):
        self.settings = values
        try:
            save_settings(self.settings)
            self._log("Settings saved.")
        except OSError as e:
            self._log(f"Couldn't save settings: {e}")

    def _warn_missing_ffmpeg(self):
        self._log("ffmpeg was not found — conversion is disabled until it's installed.")
        messagebox.showwarning("ffmpeg not found", install_instructions())

    def _start_conversion(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.ffmpeg_path = get_ffmpeg_path()
        if not self.ffmpeg_path:
            messagebox.showwarning("ffmpeg not found", install_instructions())
            return
        self.ffprobe_path = get_ffprobe_path()

        if not len(self.queue):
            self._log("No files in queue.")
            return
        if not self.output_folder:
            self._log("Please select an output folder first.")
            return

        self.queue.reset_statuses()
        for item in self.queue:
            self.queue_table.item(item["path"], values=(item["path"], "Waiting"))
        self.progress["value"] = 0

        self.cancel_event.clear()
        self._set_running(True)

        self.worker_thread = threading.Thread(target=self._run_conversion, daemon=True)
        self.worker_thread.start()

    def _cancel_conversion(self):
        if self.worker_thread and self.worker_thread.is_alive():
            self.cancel_event.set()
            self.cancel_btn.configure(state="disabled", text="Cancelling…")

    def _run_conversion(self):
        """Runs on a background thread. Never touches Tk widgets directly —
        everything goes through self.ui_events, drained on the main thread."""
        items = self.queue.snapshot()
        total = len(items)
        s = self.settings

        for i, item in enumerate(items):
            if self.cancel_event.is_set():
                self.ui_events.put(("log", "Cancelled."))
                break

            path = item["path"]

            def on_progress(fraction, path=path, i=i):
                self.ui_events.put(("file_progress", path, fraction, i, total))

            success, result = convert_file(
                path,
                self.output_folder,
                s["output_format"],
                s["bitrate"],
                s["sample_rate"],
                s["channels"],
                s["overwrite_mode"],
                ffmpeg_path=self.ffmpeg_path,
                ffprobe_path=self.ffprobe_path,
                on_progress=on_progress,
                cancel_event=self.cancel_event,
            )

            status = "✓ Done" if success else ("⏹ Cancelled" if result == "Cancelled" else "✗ Failed")
            self.queue.set_status(path, status, error=None if success else result)
            self.ui_events.put(("status", path, status))
            self.ui_events.put(("log", f"{path}: {result}" if not success else result))
            self.ui_events.put(("overall_progress", (i + 1) / total))

            if result == "Cancelled":
                break

        self.ui_events.put(("done", None))

    # ----------------------------
    # Thread-safe UI updates
    # ----------------------------
    def _drain_ui_events(self):
        try:
            while True:
                event = self.ui_events.get_nowait()
                kind = event[0]

                if kind == "log":
                    self._log(event[1])
                elif kind == "status":
                    _, path, status = event
                    if self.queue_table.exists(path):
                        self.queue_table.item(path, values=(path, status))
                elif kind == "file_progress":
                    _, path, fraction, i, total = event
                    if self.queue_table.exists(path):
                        pct = int(fraction * 100)
                        self.queue_table.item(path, values=(path, f"Converting… {pct}%"))
                    self.progress["value"] = ((i + fraction) / total) * 1000
                elif kind == "overall_progress":
                    _, fraction = event
                    self.progress["value"] = fraction * 1000
                elif kind == "done":
                    self._set_running(False)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._drain_ui_events)

    def _set_running(self, running: bool):
        state = "disabled" if running else "normal"
        for btn in (self.add_btn, self.output_btn, self.convert_btn, self.clear_btn):
            btn.configure(state=state)
        self.cancel_btn.configure(state=("normal" if running else "disabled"), text="Cancel")

    # ----------------------------
    # Helpers
    # ----------------------------
    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", msg.strip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _update_count(self):
        self.file_count_label.configure(text=f"Queue: {len(self.queue)} files")


if __name__ == "__main__":
    App().mainloop()
