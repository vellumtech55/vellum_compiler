"""
Lightweight Screen Recorder for Windows
Requirements: pip install mss opencv-python numpy pillow
Run: python screen_recorder.py
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import datetime
import mss
import cv2
import numpy as np


class ScreenRecorder:
    def __init__(self, root):
        self.root = root
        self.root.title("Screen Recorder")
        self.root.geometry("360x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f0f0f")

        self.recording = False
        self.paused = False
        self.thread = None
        self.out = None
        self.start_time = None
        self.elapsed_before_pause = 0
        self.pause_start = None
        self.output_path = ""
        self.fps = tk.IntVar(value=30)
        self.monitor_idx = tk.IntVar(value=0)
        self.timer_job = None

        # Get available monitors
        with mss.MSS() as sct:
            self.monitors = sct.monitors[1:]  # skip "all monitors" entry

        self._build_ui()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        PAD = 18
        BG = "#0f0f0f"
        CARD = "#1a1a1a"
        ACCENT = "#e63946"
        FG = "#f0f0f0"
        MUTED = "#666666"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox",
                        fieldbackground=CARD, background=CARD,
                        foreground=FG, selectbackground=CARD,
                        selectforeground=FG, bordercolor="#333", lightcolor="#333",
                        darkcolor="#333", arrowcolor=FG)

        # ── Header ──────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=PAD, pady=(PAD, 0))

        tk.Label(hdr, text="⬤", fg=ACCENT, bg=BG, font=("Segoe UI", 14)).pack(side="left")
        tk.Label(hdr, text="  Screen Recorder", fg=FG, bg=BG,
                 font=("Segoe UI", 13, "bold")).pack(side="left")

        # ── Timer ───────────────────────────────────────────────────────────
        self.timer_var = tk.StringVar(value="00:00:00")
        tk.Label(self.root, textvariable=self.timer_var,
                 fg=ACCENT, bg=BG, font=("Courier New", 32, "bold")).pack(pady=(14, 2))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self.root, textvariable=self.status_var,
                 fg=MUTED, bg=BG, font=("Segoe UI", 9)).pack()

        # ── Settings card ───────────────────────────────────────────────────
        card = tk.Frame(self.root, bg=CARD, bd=0)
        card.pack(fill="x", padx=PAD, pady=14)

        def row(parent, label, widget_fn, pady=(6, 0)):
            f = tk.Frame(parent, bg=CARD)
            f.pack(fill="x", padx=14, pady=pady)
            tk.Label(f, text=label, fg=MUTED, bg=CARD,
                     font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
            widget_fn(f)

        # Monitor selector
        mon_labels = [f"Display {i+1}  ({m['width']}×{m['height']})"
                      for i, m in enumerate(self.monitors)]
        if not mon_labels:
            mon_labels = ["Primary display"]

        self.mon_combo = ttk.Combobox(card, values=mon_labels, state="readonly",
                                      font=("Segoe UI", 9), width=22)
        self.mon_combo.current(0)
        row(card, "Monitor", lambda f: self.mon_combo.pack(side="left", pady=(0,0)), pady=(10, 0))
        self.mon_combo.pack_forget()  # re-pack inside row properly

        # Re-do monitor row cleanly
        f = tk.Frame(card, bg=CARD)
        f.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(f, text="Monitor", fg=MUTED, bg=CARD,
                 font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
        self.mon_combo = ttk.Combobox(f, values=mon_labels, state="readonly",
                                      font=("Segoe UI", 9), width=22)
        self.mon_combo.current(0)
        self.mon_combo.pack(side="left")

        # FPS row
        f2 = tk.Frame(card, bg=CARD)
        f2.pack(fill="x", padx=14, pady=(8, 10))
        tk.Label(f2, text="Frame rate", fg=MUTED, bg=CARD,
                 font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
        for fps_val in [15, 24, 30, 60]:
            active = fps_val == 30
            btn = tk.Label(f2, text=str(fps_val),
                           fg=FG if active else MUTED,
                           bg="#333" if active else CARD,
                           font=("Segoe UI", 9),
                           padx=8, pady=2, cursor="hand2", relief="flat")
            btn.pack(side="left", padx=(0, 4))
            btn.bind("<Button-1>", lambda e, v=fps_val, b=btn: self._set_fps(v))
            self._fps_buttons = getattr(self, "_fps_buttons", [])
            self._fps_buttons.append((fps_val, btn))

        self._fps_target = 30
        self._fps_btn_map = {v: b for v, b in self._fps_buttons}

        # Output path row
        f3 = tk.Frame(card, bg=CARD)
        f3.pack(fill="x", padx=14, pady=(0, 10))
        tk.Label(f3, text="Save to", fg=MUTED, bg=CARD,
                 font=("Segoe UI", 8), width=9, anchor="w").pack(side="left")
        self.path_var = tk.StringVar(value=self._default_path())
        path_entry = tk.Entry(f3, textvariable=self.path_var, bg="#111", fg=FG,
                              insertbackground=FG, relief="flat",
                              font=("Segoe UI", 8), width=18)
        path_entry.pack(side="left")
        browse_btn = tk.Label(f3, text=" ⋯", fg=MUTED, bg=CARD, cursor="hand2",
                              font=("Segoe UI", 11))
        browse_btn.pack(side="left")
        browse_btn.bind("<Button-1>", lambda e: self._browse())

        # ── Controls ────────────────────────────────────────────────────────
        ctrl = tk.Frame(self.root, bg=BG)
        ctrl.pack(pady=(0, PAD))

        self.rec_btn = tk.Button(ctrl, text="⏺  Record",
                                 command=self._toggle_record,
                                 bg=ACCENT, fg="white", relief="flat",
                                 font=("Segoe UI", 10, "bold"),
                                 padx=22, pady=9, cursor="hand2",
                                 activebackground="#c1121f", activeforeground="white")
        self.rec_btn.pack(side="left", padx=(0, 8))

        self.pause_btn = tk.Button(ctrl, text="⏸  Pause",
                                   command=self._toggle_pause,
                                   bg="#2a2a2a", fg=MUTED, relief="flat",
                                   font=("Segoe UI", 10),
                                   padx=16, pady=9, cursor="hand2",
                                   activebackground="#333", activeforeground=FG,
                                   state="disabled")
        self.pause_btn.pack(side="left")

        # ── Footer ──────────────────────────────────────────────────────────
        tk.Label(self.root, text="Saves as .mp4  ·  No audio",
                 fg="#333", bg=BG, font=("Segoe UI", 8)).pack()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _default_path(self):
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        if not os.path.isdir(desktop):
            desktop = os.path.expanduser("~")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(desktop, f"recording_{ts}.mp4")

    def _set_fps(self, val):
        self._fps_target = val
        MUTED = "#666666"
        FG = "#f0f0f0"
        for v, b in self._fps_btn_map.items():
            b.configure(fg=FG if v == val else MUTED,
                        bg="#333" if v == val else "#1a1a1a")

    def _browse(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 video", "*.mp4")],
            initialfile=os.path.basename(self.path_var.get()),
            initialdir=os.path.dirname(self.path_var.get()))
        if path:
            self.path_var.set(path)

    # ── Recording logic ──────────────────────────────────────────────────────

    def _toggle_record(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _toggle_pause(self):
        if not self.paused:
            self.paused = True
            self.pause_start = time.time()
            self.elapsed_before_pause += self.pause_start - self.start_time
            self.status_var.set("Paused")
            self.pause_btn.configure(text="▶  Resume", fg="#f0f0f0")
        else:
            self.paused = False
            self.start_time = time.time()
            self.status_var.set("Recording…")
            self.pause_btn.configure(text="⏸  Pause", fg="#666")

    def _start_recording(self):
        path = self.path_var.get()
        if not path:
            messagebox.showerror("Error", "Please choose an output path.")
            return

        mon_idx = self.mon_combo.current()
        if mon_idx < 0:
            mon_idx = 0

        with mss.MSS() as sct:
            monitors = sct.monitors[1:]
            if not monitors:
                messagebox.showerror("Error", "No monitors detected.")
                return
            mon = monitors[min(mon_idx, len(monitors) - 1)]

        w, h = mon["width"], mon["height"]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.out = cv2.VideoWriter(path, fourcc, self._fps_target, (w, h))
        if not self.out.isOpened():
            messagebox.showerror("Error", f"Could not open output file:\n{path}")
            return

        self.recording = True
        self.paused = False
        self.elapsed_before_pause = 0
        self.start_time = time.time()
        self.output_path = path

        self.rec_btn.configure(text="⏹  Stop", bg="#333", fg="#f0f0f0",
                               activebackground="#444")
        self.pause_btn.configure(state="normal", fg="#666")
        self.status_var.set("Recording…")
        self._update_timer()

        self.thread = threading.Thread(
            target=self._record_loop,
            args=(mon, self._fps_target),
            daemon=True)
        self.thread.start()

    def _stop_recording(self):
        self.recording = False
        if self.timer_job:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None

        self.rec_btn.configure(text="⏺  Record", bg="#e63946", fg="white",
                               activebackground="#c1121f")
        self.pause_btn.configure(state="disabled", text="⏸  Pause", fg="#666")
        self.status_var.set(f"Saved → {os.path.basename(self.output_path)}")
        self.timer_var.set("00:00:00")

        # Reset path for next recording
        self.path_var.set(self._default_path())

    def _record_loop(self, mon, fps):
        interval = 1.0 / fps
        with mss.MSS() as sct:
            while self.recording:
                t0 = time.perf_counter()
                if not self.paused:
                    img = sct.grab(mon)
                    frame = np.array(img)
                    # mss returns BGRA; drop alpha → BGR
                    frame = frame[:, :, :3]
                    self.out.write(frame)
                elapsed = time.perf_counter() - t0
                wait = interval - elapsed
                if wait > 0:
                    time.sleep(wait)
        if self.out:
            self.out.release()
            self.out = None

    def _update_timer(self):
        if not self.recording:
            return
        if not self.paused:
            elapsed = self.elapsed_before_pause + (time.time() - self.start_time)
        else:
            elapsed = self.elapsed_before_pause
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        self.timer_var.set(f"{h:02d}:{m:02d}:{s:02d}")
        self.timer_job = self.root.after(500, self._update_timer)


def main():
    root = tk.Tk()
    app = ScreenRecorder(root)
    root.mainloop()


if __name__ == "__main__":
    main()
