

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ----------------------------------------------------------------------
# Brand theme — Vellum navy / silver
# ----------------------------------------------------------------------
NAVY_DARKEST = "#070D19"
NAVY_DARK    = "#0C1930"
NAVY         = "#132445"
NAVY_LIGHT   = "#1D3260"
NAVY_BORDER  = "#2A4272"

SILVER       = "#C7CFDD"
SILVER_LIGHT = "#EDF1F7"
SILVER_DIM   = "#8892A6"

ACCENT       = "#5C87C9"   # steel-blue accent, reads as "polished silver-blue"
ACCENT_HOVER = "#729BDA"
ACCENT_DIM   = "#3B5A8A"

DANGER       = "#C97A7A"
SUCCESS      = "#7AC9A0"

FONT_FAMILY = "Segoe UI"

# ----------------------------------------------------------------------
# Conversion presets
# ----------------------------------------------------------------------
CONTAINERS = ["mp4", "mkv", "mov", "avi", "webm", "gif", "mp3 (audio only)"]

QUALITY_PRESETS = {
    "High quality (larger file)":   {"crf": 18, "preset": "slow"},
    "Balanced (recommended)":       {"crf": 23, "preset": "medium"},
    "Small file (faster)":          {"crf": 28, "preset": "fast"},
    "Fastest (lowest quality)":     {"crf": 32, "preset": "ultrafast"},
}

RESOLUTIONS = {
    "Keep original": None,
    "1080p (1920x1080)": "1920:1080",
    "720p (1280x720)": "1280:720",
    "480p (854x480)": "854:480",
}

CODEC_BY_CONTAINER = {
    "mp4":  ("libx264", "aac"),
    "mkv":  ("libx264", "aac"),
    "mov":  ("libx264", "aac"),
    "avi":  ("mpeg4", "mp3"),
    "webm": ("libvpx-vp9", "libopus"),
}


def get_ffmpeg_paths():
    """Locate ffmpeg/ffprobe: bundled folder first, then system PATH."""
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    bundled_dir = os.path.join(base_dir, "ffmpeg")
    exe_suffix = ".exe" if os.name == "nt" else ""

    ffmpeg_bundled = os.path.join(bundled_dir, f"ffmpeg{exe_suffix}")
    ffprobe_bundled = os.path.join(bundled_dir, f"ffprobe{exe_suffix}")

    if os.path.isfile(ffmpeg_bundled) and os.path.isfile(ffprobe_bundled):
        return ffmpeg_bundled, ffprobe_bundled

    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")
    return ffmpeg_path, ffprobe_path


def subprocess_flags():
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def probe_duration(ffprobe_path, filepath):
    """Return duration in seconds (float) or None."""
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "quiet", "-print_format", "json",
             "-show_format", filepath],
            capture_output=True, text=True, timeout=30, **subprocess_flags()
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception:
        return None


def format_duration(seconds):
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_size(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return "--"
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ----------------------------------------------------------------------
# Job model
# ----------------------------------------------------------------------
class Job:
    def __init__(self, filepath):
        self.filepath = filepath
        self.name = os.path.basename(filepath)
        self.duration = None
        self.status = "Queued"
        self.progress = 0.0
        self.output_path = None
        self.error = None


# ----------------------------------------------------------------------
# Main app
# ----------------------------------------------------------------------
class VellumVideoConverter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Vellum Video Converter")
        self.geometry("880x620")
        self.minsize(760, 540)
        self.configure(bg=NAVY_DARKEST)

        self.ffmpeg_path, self.ffprobe_path = get_ffmpeg_paths()

        self.jobs = []
        self.output_dir = tk.StringVar(value="")
        self.container_var = tk.StringVar(value=CONTAINERS[0])
        self.quality_var = tk.StringVar(value="Balanced (recommended)")
        self.resolution_var = tk.StringVar(value="Keep original")

        self.worker_thread = None
        self.cancel_event = threading.Event()
        self.ui_queue = queue.Queue()
        self.is_running = False

        self._build_style()
        self._build_layout()
        self._poll_queue()

        if not self.ffmpeg_path or not self.ffprobe_path:
            self._log("ffmpeg/ffprobe not found. Place ffmpeg.exe and "
                       "ffprobe.exe in a 'ffmpeg' folder next to this app, "
                       "or install ffmpeg and add it to PATH.", warn=True)

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=NAVY_DARKEST)
        style.configure("Panel.TFrame", background=NAVY_DARK)
        style.configure("TLabel", background=NAVY_DARKEST, foreground=SILVER,
                         font=(FONT_FAMILY, 10))
        style.configure("Panel.TLabel", background=NAVY_DARK, foreground=SILVER,
                         font=(FONT_FAMILY, 10))
        style.configure("Header.TLabel", background=NAVY_DARKEST, foreground=SILVER_LIGHT,
                         font=(FONT_FAMILY, 18, "bold"))
        style.configure("Sub.TLabel", background=NAVY_DARKEST, foreground=SILVER_DIM,
                         font=(FONT_FAMILY, 9))
        style.configure("SectionTitle.TLabel", background=NAVY_DARK, foreground=SILVER_LIGHT,
                         font=(FONT_FAMILY, 10, "bold"))

        style.configure("TButton", background=NAVY_LIGHT, foreground=SILVER_LIGHT,
                         borderwidth=0, focusthickness=0, padding=(12, 8),
                         font=(FONT_FAMILY, 9, "bold"))
        style.map("TButton",
                  background=[("active", NAVY_BORDER), ("disabled", NAVY)],
                  foreground=[("disabled", SILVER_DIM)])

        style.configure("Accent.TButton", background=ACCENT, foreground=NAVY_DARKEST,
                         borderwidth=0, padding=(16, 10), font=(FONT_FAMILY, 10, "bold"))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_HOVER), ("disabled", ACCENT_DIM)],
                  foreground=[("disabled", SILVER_DIM)])

        style.configure("Danger.TButton", background=NAVY_LIGHT, foreground=DANGER,
                         borderwidth=0, padding=(12, 8), font=(FONT_FAMILY, 9, "bold"))
        style.map("Danger.TButton", background=[("active", NAVY_BORDER)])

        style.configure("TCombobox", fieldbackground=NAVY_LIGHT, background=NAVY_LIGHT,
                         foreground=SILVER_LIGHT, arrowcolor=SILVER,
                         bordercolor=NAVY_BORDER, lightcolor=NAVY_LIGHT, darkcolor=NAVY_LIGHT,
                         padding=6)
        style.map("TCombobox", fieldbackground=[("readonly", NAVY_LIGHT)])
        self.option_add("*TCombobox*Listbox.background", NAVY_LIGHT)
        self.option_add("*TCombobox*Listbox.foreground", SILVER_LIGHT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT_DIM)

        style.configure("Horizontal.TProgressbar", troughcolor=NAVY,
                         background=ACCENT, bordercolor=NAVY, lightcolor=ACCENT,
                         darkcolor=ACCENT, thickness=10)

        style.configure("Treeview", background=NAVY_DARK, fieldbackground=NAVY_DARK,
                         foreground=SILVER_LIGHT, borderwidth=0, rowheight=26,
                         font=(FONT_FAMILY, 9))
        style.configure("Treeview.Heading", background=NAVY, foreground=SILVER_DIM,
                         borderwidth=0, font=(FONT_FAMILY, 9, "bold"))
        style.map("Treeview", background=[("selected", ACCENT_DIM)],
                  foreground=[("selected", SILVER_LIGHT)])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        root = ttk.Frame(self, style="TFrame", padding=20)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        # Header
        header = ttk.Frame(root, style="TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(header, text="VELLUM VIDEO CONVERTER", style="Header.TLabel").pack(anchor="w")
        ttk.Label(header, text="Batch convert video & audio files — local, private, no cloud.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))

        sep = tk.Frame(root, bg=NAVY_BORDER, height=1)
        sep.grid(row=1, column=0, sticky="ew", pady=(14, 14))

        # Options panel
        options = ttk.Frame(root, style="Panel.TFrame", padding=16)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        for c in range(4):
            options.columnconfigure(c, weight=1)

        ttk.Label(options, text="Output format", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, textvariable=self.container_var, values=CONTAINERS,
                     state="readonly").grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))

        ttk.Label(options, text="Quality", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Combobox(options, textvariable=self.quality_var, values=list(QUALITY_PRESETS.keys()),
                     state="readonly").grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(4, 0))

        ttk.Label(options, text="Resolution", style="Panel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Combobox(options, textvariable=self.resolution_var, values=list(RESOLUTIONS.keys()),
                     state="readonly").grid(row=1, column=2, sticky="ew", padx=(0, 10), pady=(4, 0))

        out_frame = ttk.Frame(options, style="Panel.TFrame")
        out_frame.grid(row=0, column=3, rowspan=2, sticky="ew")
        ttk.Label(out_frame, text="Output folder", style="Panel.TLabel").pack(anchor="w")
        row = ttk.Frame(out_frame, style="Panel.TFrame")
        row.pack(fill="x", pady=(4, 0))
        self.output_entry = tk.Entry(row, textvariable=self.output_dir, bg=NAVY_LIGHT,
                                      fg=SILVER_LIGHT, insertbackground=SILVER_LIGHT,
                                      relief="flat", highlightthickness=1,
                                      highlightbackground=NAVY_BORDER, highlightcolor=ACCENT)
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=4)
        ttk.Button(row, text="Browse", command=self._choose_output_dir).pack(side="left", padx=(6, 0))

        # File list
        list_frame = ttk.Frame(root, style="Panel.TFrame", padding=12)
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(1, weight=1)

        list_header = ttk.Frame(list_frame, style="Panel.TFrame")
        list_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(list_header, text="QUEUE", style="SectionTitle.TLabel").pack(side="left")
        btns = ttk.Frame(list_header, style="Panel.TFrame")
        btns.pack(side="right")
        ttk.Button(btns, text="Add Files", command=self._add_files).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Remove Selected", command=self._remove_selected).pack(side="left", padx=(0, 6))
        ttk.Button(btns, text="Clear", command=self._clear_queue).pack(side="left")

        columns = ("name", "duration", "status", "progress")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("name", text="File")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("status", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.column("name", width=380, anchor="w")
        self.tree.column("duration", width=90, anchor="center")
        self.tree.column("status", width=130, anchor="center")
        self.tree.column("progress", width=100, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky="ns")

        # Log
        log_frame = ttk.Frame(root, style="Panel.TFrame", padding=(12, 8))
        log_frame.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        ttk.Label(log_frame, text="LOG", style="SectionTitle.TLabel").pack(anchor="w")
        self.log_text = tk.Text(log_frame, height=6, bg=NAVY_DARKEST, fg=SILVER,
                                 insertbackground=SILVER, relief="flat", wrap="word",
                                 font=("Consolas", 9))
        self.log_text.pack(fill="x", pady=(6, 0))
        self.log_text.configure(state="disabled")

        # Footer / controls
        footer = ttk.Frame(root, style="TFrame")
        footer.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        footer.columnconfigure(0, weight=1)

        self.overall_progress = ttk.Progressbar(footer, style="Horizontal.TProgressbar",
                                                 mode="determinate")
        self.overall_progress.grid(row=0, column=0, sticky="ew", padx=(0, 14))

        self.start_button = ttk.Button(footer, text="Start Conversion", style="Accent.TButton",
                                        command=self._start_conversion)
        self.start_button.grid(row=0, column=1)

        self.cancel_button = ttk.Button(footer, text="Cancel", style="Danger.TButton",
                                         command=self._cancel_conversion, state="disabled")
        self.cancel_button.grid(row=0, column=2, padx=(8, 0))

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select video files",
            filetypes=[("Video/Audio files",
                        "*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v *.mp3 *.wav *.aac *.flac"),
                       ("All files", "*.*")]
        )
        for p in paths:
            job = Job(p)
            if self.ffprobe_path:
                job.duration = probe_duration(self.ffprobe_path, p)
            self.jobs.append(job)
            self.tree.insert("", "end", iid=str(len(self.jobs) - 1),
                              values=(job.name, format_duration(job.duration), job.status, "0%"))

        if not self.output_dir.get() and paths:
            self.output_dir.set(os.path.dirname(paths[0]))

    def _remove_selected(self):
        if self.is_running:
            return
        selected = self.tree.selection()
        for iid in selected:
            self.tree.delete(iid)
        self._reindex_jobs()

    def _clear_queue(self):
        if self.is_running:
            return
        self.tree.delete(*self.tree.get_children())
        self.jobs = []

    def _reindex_jobs(self):
        remaining_iids = self.tree.get_children()
        old_jobs = self.jobs
        new_jobs = []
        new_tree_data = []
        for iid in remaining_iids:
            idx = int(iid)
            new_jobs.append(old_jobs[idx])
            new_tree_data.append(self.tree.item(iid, "values"))
        self.tree.delete(*self.tree.get_children())
        self.jobs = new_jobs
        for i, job in enumerate(self.jobs):
            self.tree.insert("", "end", iid=str(i),
                              values=(job.name, format_duration(job.duration), job.status, "0%"))

    def _choose_output_dir(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.output_dir.set(d)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _log(self, message, warn=False):
        self.log_text.configure(state="normal")
        prefix = "[!] " if warn else "[i] "
        self.log_text.insert("end", prefix + message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Conversion control
    # ------------------------------------------------------------------
    def _start_conversion(self):
        if self.is_running:
            return
        if not self.jobs:
            messagebox.showinfo("Vellum Video Converter", "Add at least one file first.")
            return
        if not self.ffmpeg_path or not self.ffprobe_path:
            messagebox.showerror("Vellum Video Converter",
                                  "ffmpeg/ffprobe not found. See log for details.")
            return
        out_dir = self.output_dir.get().strip()
        if not out_dir:
            messagebox.showinfo("Vellum Video Converter", "Choose an output folder.")
            return
        os.makedirs(out_dir, exist_ok=True)

        for i, job in enumerate(self.jobs):
            job.status = "Queued"
            job.progress = 0.0
            self.tree.set(str(i), "status", "Queued")
            self.tree.set(str(i), "progress", "0%")

        self.cancel_event.clear()
        self.is_running = True
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.overall_progress["value"] = 0

        self.worker_thread = threading.Thread(target=self._run_queue, args=(out_dir,), daemon=True)
        self.worker_thread.start()

    def _cancel_conversion(self):
        self.cancel_event.set()
        self._log("Cancelling after current file finishes...", warn=True)
        self.cancel_button.configure(state="disabled")

    def _run_queue(self, out_dir):
        total = len(self.jobs)
        for i, job in enumerate(self.jobs):
            if self.cancel_event.is_set():
                job.status = "Cancelled"
                self.ui_queue.put(("status", i, "Cancelled"))
                continue
            self.ui_queue.put(("status", i, "Converting..."))
            self.ui_queue.put(("log", f"Converting {job.name}..."))
            ok, err = self._convert_job(job, i, out_dir)
            if self.cancel_event.is_set() and not ok:
                self.ui_queue.put(("status", i, "Cancelled"))
            elif ok:
                self.ui_queue.put(("status", i, "Done"))
                self.ui_queue.put(("progress", i, 100))
                self.ui_queue.put(("log", f"Finished {job.name} -> "
                                           f"{format_size(job.output_path)}"))
            else:
                self.ui_queue.put(("status", i, "Error"))
                self.ui_queue.put(("log", f"Failed {job.name}: {err}"))
            self.ui_queue.put(("overall", i + 1, total))

        self.ui_queue.put(("done", None, None))

    def _convert_job(self, job, index, out_dir):
        container_choice = self.container_var.get()
        is_audio_only = container_choice.startswith("mp3")
        ext = "mp3" if is_audio_only else container_choice
        quality = QUALITY_PRESETS[self.quality_var.get()]
        resolution = RESOLUTIONS[self.resolution_var.get()]

        base_name = os.path.splitext(job.name)[0]
        output_path = os.path.join(out_dir, f"{base_name}.{ext}")
        # avoid overwriting an existing file of the same name
        counter = 1
        while os.path.exists(output_path):
            output_path = os.path.join(out_dir, f"{base_name}_{counter}.{ext}")
            counter += 1
        job.output_path = output_path

        cmd = [self.ffmpeg_path, "-y", "-i", job.filepath]

        if is_audio_only:
            cmd += ["-vn", "-b:a", "192k"]
        else:
            video_codec, audio_codec = CODEC_BY_CONTAINER.get(ext, ("libx264", "aac"))
            if ext == "gif":
                vf = "fps=12,scale=480:-1:flags=lanczos"
                if resolution:
                    w = resolution.split(":")[0]
                    vf = f"fps=12,scale={w}:-1:flags=lanczos"
                cmd += ["-vf", vf, "-loop", "0"]
            else:
                cmd += ["-c:v", video_codec, "-crf", str(quality["crf"]),
                        "-preset", quality["preset"], "-c:a", audio_codec]
                if resolution:
                    cmd += ["-vf", f"scale={resolution}"]

        cmd += ["-progress", "pipe:1", "-nostats", output_path]

        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, **subprocess_flags()
            )
        except Exception as e:
            return False, str(e)

        last_error_lines = []
        while True:
            if self.cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except OSError:
                        pass
                return False, "Cancelled by user"

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    break
                continue

            last_error_lines.append(line.strip())
            if len(last_error_lines) > 15:
                last_error_lines.pop(0)

            match = re.search(r"out_time_ms=(\d+)", line)
            if match and job.duration:
                out_time_s = int(match.group(1)) / 1_000_000
                pct = min(100, (out_time_s / job.duration) * 100)
                self.ui_queue.put(("progress", index, pct))

        returncode = process.wait()
        if returncode != 0:
            error_text = " | ".join(last_error_lines[-4:]) if last_error_lines else "Unknown ffmpeg error"
            return False, error_text
        return True, None

    # ------------------------------------------------------------------
    # UI queue polling (worker -> main thread)
    # ------------------------------------------------------------------
    def _poll_queue(self):
        try:
            while True:
                kind, a, b = self.ui_queue.get_nowait()
                if kind == "status":
                    self.tree.set(str(a), "status", b)
                elif kind == "progress":
                    self.tree.set(str(a), "progress", f"{b:.0f}%")
                elif kind == "overall":
                    completed, total = a, b
                    self.overall_progress["value"] = (completed / total) * 100
                elif kind == "log":
                    self._log(a)
                elif kind == "done":
                    self.is_running = False
                    self.start_button.configure(state="normal")
                    self.cancel_button.configure(state="disabled")
                    self._log("Queue finished.")
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)


if __name__ == "__main__":
    app = VellumVideoConverter()
    app.mainloop()
