# tool/editor_page.py — AI Video Editor UI
# Drop-in ToolPage that VellumTool._mount_tool() loads automatically.

import os
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk


class EditorPage(tk.Frame):
    """Main editor UI — file picker, settings, progress, log."""

    def __init__(self, parent, app):
        t = app.colors
        super().__init__(parent, bg=t["bg"])
        self._app   = app
        self._t     = t
        self._video = tk.StringVar()
        self._outdir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Videos", "Vellum"))
        self._mode  = tk.StringVar(value="single")
        self._thresh = tk.DoubleVar(value=0.03)

        # Game HUD detection (beta) — visual, not audio: two screen regions
        # dragged out in the UI (damage flash + ammo counter).
        self._game_vision   = tk.BooleanVar(value=False)
        self._damage_region = None   # (x1,y1,x2,y2) fractions 0-1, set via _open_region_picker
        self._ammo_region   = None

        # Voice-activity-detection backend: "ffmpeg" (fast, amplitude-based)
        # or "silero" (neural VAD via onnxruntime, beta — CPU or GPU).
        self._vad_backend  = tk.StringVar(value="ffmpeg")
        self._vad_device   = tk.StringVar(value="cpu")
        self._silero_thresh = tk.DoubleVar(value=0.5)

        self._running = False

        self._build()

    # ─────────────────────────────────────────────────────────────────────────
    # Layout
    # ─────────────────────────────────────────────────────────────────────────
    def _build(self):
        t = self._t

        # Two-column layout: left = controls (fixed), right = log (flex)
        self.grid_columnconfigure(0, minsize=340, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── LEFT PANEL ───────────────────────────────────────────────────────
        left = tk.Frame(self, bg=t["bg"], padx=24, pady=24)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        row = 0

        # Section: Input
        self._section(left, row, "Input"); row += 1

        self._field_label(left, row, "Video file"); row += 1
        pick_row = tk.Frame(left, bg=t["bg"])
        pick_row.grid(row=row, column=0, sticky="ew", pady=(0, 12)); row += 1
        pick_row.grid_columnconfigure(0, weight=1)

        self._video_entry = ctk.CTkEntry(
            pick_row, textvariable=self._video,
            placeholder_text="No file selected",
            fg_color=t["panel"], border_color=t["border"],
            text_color=t["text"], placeholder_text_color=t["text_dim"],
            font=("Segoe UI", 10), height=34, corner_radius=6,
        )
        self._video_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            pick_row, text="Browse",
            command=self._browse_video,
            fg_color=t["accent"], hover_color=t["accent_hover"],
            text_color=t["btn_text"],
            font=("Segoe UI", 10, "bold"), height=34, corner_radius=6, width=80,
        ).grid(row=0, column=1)

        # Output folder
        self._field_label(left, row, "Output folder"); row += 1
        out_row = tk.Frame(left, bg=t["bg"])
        out_row.grid(row=row, column=0, sticky="ew", pady=(0, 20)); row += 1
        out_row.grid_columnconfigure(0, weight=1)

        ctk.CTkEntry(
            out_row, textvariable=self._outdir,
            fg_color=t["panel"], border_color=t["border"],
            text_color=t["text"],
            font=("Segoe UI", 10), height=34, corner_radius=6,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            out_row, text="Browse",
            command=self._browse_outdir,
            fg_color=t["panel_alt"], hover_color=t["border"],
            text_color=t["text"],
            font=("Segoe UI", 10), height=34, corner_radius=6, width=80,
        ).grid(row=0, column=1)

        # Divider
        tk.Frame(left, bg=t["border"], height=1).grid(
            row=row, column=0, sticky="ew", pady=(4, 16)); row += 1

        # Section: Settings
        self._section(left, row, "Settings"); row += 1

        # Output mode
        self._field_label(left, row, "Output mode"); row += 1
        mode_row = tk.Frame(left, bg=t["bg"])
        mode_row.grid(row=row, column=0, sticky="ew", pady=(0, 12)); row += 1

        for label, val in [("Single file", "single"), ("Separate clips", "multiple")]:
            rb = tk.Radiobutton(
                mode_row, text=label, variable=self._mode, value=val,
                font=("Segoe UI", 10), fg=t["text"], bg=t["bg"],
                activeforeground=t["accent"], activebackground=t["bg"],
                selectcolor=t["panel_alt"],
                relief="flat", bd=0,
            )
            rb.pack(side="left", padx=(0, 16))

        # Voice detection engine (VAD backend)
        self._field_label(left, row, "Voice detection engine"); row += 1
        backend_row = tk.Frame(left, bg=t["bg"])
        backend_row.grid(row=row, column=0, sticky="ew", pady=(0, 4)); row += 1
        backend_row.grid_columnconfigure(0, weight=1)

        self._backend_menu = ctk.CTkOptionMenu(
            backend_row,
            values=["ffmpeg (fast)", "Silero VAD (ONNX, beta)"],
            command=self._on_backend_change,
            fg_color=t["panel"], button_color=t["accent"],
            button_hover_color=t["accent_hover"],
            dropdown_fg_color=t["panel"], dropdown_hover_color=t["panel_alt"],
            text_color=t["text"], font=("Segoe UI", 10),
            height=32, corner_radius=6,
        )
        self._backend_menu.set("ffmpeg (fast)")
        self._backend_menu.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._device_menu = ctk.CTkOptionMenu(
            backend_row,
            values=["CPU", "GPU"],
            command=lambda v: self._vad_device.set(v.lower()),
            fg_color=t["panel_alt"], button_color=t["accent"],
            button_hover_color=t["accent_hover"],
            dropdown_fg_color=t["panel"], dropdown_hover_color=t["panel_alt"],
            text_color=t["text"], font=("Segoe UI", 10),
            height=32, corner_radius=6, width=80,
        )
        self._device_menu.set("CPU")
        self._device_menu.grid(row=0, column=1)
        self._device_menu.grid_remove()  # only shown once Silero is selected

        self._backend_hint = tk.Label(
            left,
            text="ffmpeg: fast, amplitude-based. Silero: neural VAD, more accurate around music/game audio.",
            font=("Segoe UI", 8), fg=t["text_dim"], bg=t["bg"],
            wraplength=290, justify="left",
        )
        self._backend_hint.grid(row=row, column=0, sticky="w", pady=(0, 14)); row += 1

        # Sensitivity — ffmpeg amplitude threshold OR Silero speech-probability
        # threshold, whichever backend is active. Both rows share the same
        # grid slot and toggle visibility in _on_backend_change().
        self._sensitivity_lbl = tk.Label(
            left, text="Voice sensitivity",
            font=("Segoe UI", 10), fg=t["text_muted"], bg=t["bg"], anchor="w",
        )
        self._sensitivity_lbl.grid(row=row, column=0, sticky="w", pady=(0, 4)); row += 1

        thresh_row = tk.Frame(left, bg=t["bg"])
        thresh_row.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        thresh_row.grid_columnconfigure(0, weight=1)
        self._thresh_row = thresh_row

        self._thresh_lbl = tk.Label(
            thresh_row, text=f"{self._thresh.get():.3f}",
            font=("Segoe UI", 10, "bold"),
            fg=t["accent"], bg=t["bg"], width=5,
        )
        self._thresh_lbl.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkSlider(
            thresh_row,
            from_=0.005, to=0.15,
            variable=self._thresh,
            command=self._on_thresh,
            button_color=t["accent"],
            button_hover_color=t["accent_hover"],
            progress_color=t["accent"],
            fg_color=t["border"],
            height=16,
        ).grid(row=0, column=0, sticky="ew")

        silero_row = tk.Frame(left, bg=t["bg"])
        silero_row.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        silero_row.grid_columnconfigure(0, weight=1)
        self._silero_row = silero_row

        self._silero_lbl = tk.Label(
            silero_row, text=f"{self._silero_thresh.get():.2f}",
            font=("Segoe UI", 10, "bold"),
            fg=t["accent"], bg=t["bg"], width=5,
        )
        self._silero_lbl.grid(row=0, column=1, padx=(8, 0))

        ctk.CTkSlider(
            silero_row,
            from_=0.1, to=0.9,
            variable=self._silero_thresh,
            command=self._on_silero_thresh,
            button_color=t["accent"],
            button_hover_color=t["accent_hover"],
            progress_color=t["accent"],
            fg_color=t["border"],
            height=16,
        ).grid(row=0, column=0, sticky="ew")
        silero_row.grid_remove()  # hidden until Silero backend selected

        row += 1

        self._sensitivity_hint = tk.Label(
            left,
            text="Lower = more sensitive (picks up quieter speech)",
            font=("Segoe UI", 8), fg=t["text_dim"], bg=t["bg"],
        )
        self._sensitivity_hint.grid(row=row, column=0, sticky="w", pady=(0, 14)); row += 1

        # Game HUD toggle
        game_row = tk.Frame(left, bg=t["bg"])
        game_row.grid(row=row, column=0, sticky="ew", pady=(0, 4)); row += 1

        ctk.CTkCheckBox(
            game_row,
            text="Game HUD detection (beta)",
            variable=self._game_vision,
            font=("Segoe UI", 10), text_color=t["text"],
            fg_color=t["accent"], hover_color=t["accent_hover"],
            checkmark_color=t["btn_text"],
            border_color=t["border"],
            corner_radius=4, height=20,
        ).pack(anchor="w")

        tk.Label(
            left,
            text="Flags damage flashes and ammo-counter shots straight from the HUD — no audio involved",
            font=("Segoe UI", 8), fg=t["text_dim"], bg=t["bg"],
            wraplength=290, justify="left",
        ).grid(row=row, column=0, sticky="w", pady=(0, 8)); row += 1

        region_row = tk.Frame(left, bg=t["bg"])
        region_row.grid(row=row, column=0, sticky="ew", pady=(0, 20)); row += 1
        region_row.grid_columnconfigure(0, weight=1)
        region_row.grid_columnconfigure(1, weight=1)

        dmg_col = tk.Frame(region_row, bg=t["bg"])
        dmg_col.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ctk.CTkButton(
            dmg_col, text="Set damage region…",
            command=lambda: self._open_region_picker("damage"),
            fg_color=t["panel_alt"], hover_color=t["border"],
            text_color=t["text"], font=("Segoe UI", 9),
            height=28, corner_radius=6, width=140,
        ).pack(anchor="w")
        self._damage_status = tk.Label(
            dmg_col, text="not set",
            font=("Segoe UI", 8), fg=t["text_dim"], bg=t["bg"],
        )
        self._damage_status.pack(anchor="w", pady=(2, 0))

        ammo_col = tk.Frame(region_row, bg=t["bg"])
        ammo_col.grid(row=0, column=1, sticky="w")
        ctk.CTkButton(
            ammo_col, text="Set ammo region…",
            command=lambda: self._open_region_picker("ammo"),
            fg_color=t["panel_alt"], hover_color=t["border"],
            text_color=t["text"], font=("Segoe UI", 9),
            height=28, corner_radius=6, width=140,
        ).pack(anchor="w")
        self._ammo_status = tk.Label(
            ammo_col, text="not set",
            font=("Segoe UI", 8), fg=t["text_dim"], bg=t["bg"],
        )
        self._ammo_status.pack(anchor="w", pady=(2, 0))

        # Divider
        tk.Frame(left, bg=t["border"], height=1).grid(
            row=row, column=0, sticky="ew", pady=(0, 20)); row += 1

        # Run button
        self._run_btn = ctk.CTkButton(
            left,
            text="▶  Process Video",
            command=self._run,
            fg_color=t["accent"], hover_color=t["accent_hover"],
            text_color=t["btn_text"],
            font=("Segoe UI", 12, "bold"),
            height=44, corner_radius=8,
        )
        self._run_btn.grid(row=row, column=0, sticky="ew"); row += 1

        # Progress bar
        self._progress_var = tk.DoubleVar(value=0)
        self._progress = ctk.CTkProgressBar(
            left,
            variable=self._progress_var,
            progress_color=t["accent"],
            fg_color=t["border"],
            corner_radius=4, height=6,
        )
        self._progress.grid(row=row, column=0, sticky="ew", pady=(10, 0)); row += 1
        self._progress.grid_remove()   # hidden until processing

        # ── RIGHT PANEL: Log ─────────────────────────────────────────────────
        right = tk.Frame(self, bg=t["bg"], pady=24)
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 24))
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # Log header
        log_hdr = tk.Frame(right, bg=t["bg"])
        log_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        tk.Label(
            log_hdr, text="Activity Log",
            font=("Segoe UI", 11, "bold"),
            fg=t["text"], bg=t["bg"],
        ).pack(side="left")

        ctk.CTkButton(
            log_hdr, text="Clear",
            command=self._clear_log,
            fg_color=t["panel_alt"], hover_color=t["border"],
            text_color=t["text_muted"],
            font=("Segoe UI", 9), height=26, corner_radius=5, width=54,
        ).pack(side="right")

        # Log box
        log_frame = tk.Frame(right, bg=t["panel"],
                             highlightbackground=t["border"],
                             highlightthickness=1)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self._log = tk.Text(
            log_frame,
            font=("Consolas", 9),
            fg=t["text_muted"], bg=t["panel"],
            relief="flat", wrap="word",
            state="disabled",
            padx=14, pady=10,
        )
        self._log.grid(row=0, column=0, sticky="nsew")

        sb = tk.Scrollbar(log_frame, command=self._log.yview,
                          bg=t["panel_alt"], troughcolor=t["panel"])
        sb.grid(row=0, column=1, sticky="ns")
        self._log["yscrollcommand"] = sb.set

        # Tag colours for log levels
        self._log.tag_configure("info",    foreground=t["text_muted"])
        self._log.tag_configure("success", foreground=t["success"])
        self._log.tag_configure("warning", foreground=t["warning"])
        self._log.tag_configure("error",   foreground=t["error"])
        self._log.tag_configure("bold",    font=("Consolas", 9, "bold"))

        self._log_line("Vellum automatic video editor — ready.", "info")
        self._log_line("Select a video file and click Process Video.", "info")

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────
    def _section(self, parent, row, text):
        t = self._t
        tk.Label(
            parent, text=text.upper(),
            font=("Segoe UI", 8, "bold"),
            fg=t["text_dim"], bg=t["bg"],
            anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=(0, 8))

    def _field_label(self, parent, row, text):
        t = self._t
        tk.Label(
            parent, text=text,
            font=("Segoe UI", 10),
            fg=t["text_muted"], bg=t["bg"],
            anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=(0, 4))

    def _on_thresh(self, val):
        self._thresh_lbl.configure(text=f"{float(val):.3f}")

    def _on_silero_thresh(self, val):
        self._silero_lbl.configure(text=f"{float(val):.2f}")

    def _on_backend_change(self, label):
        is_silero = label.startswith("Silero")
        self._vad_backend.set("silero" if is_silero else "ffmpeg")

        if is_silero:
            self._device_menu.grid()
            self._thresh_row.grid_remove()
            self._silero_row.grid()
            self._sensitivity_lbl.configure(text="Speech confidence")
            self._sensitivity_hint.configure(
                text="Higher = stricter (needs a stronger speech signal to keep a segment)"
            )
        else:
            self._device_menu.grid_remove()
            self._silero_row.grid_remove()
            self._thresh_row.grid()
            self._sensitivity_lbl.configure(text="Voice sensitivity")
            self._sensitivity_hint.configure(
                text="Lower = more sensitive (picks up quieter speech)"
            )

        self._log_line(f"Voice detection engine: {label}", "info")

    def _open_region_picker(self, kind):
        """kind: 'damage' or 'ammo'. Grabs a frame from the selected video and
        lets the user drag a box over that HUD element; stores the box as
        fractional (x1, y1, x2, y2) coordinates so it lines up regardless of
        the video's actual resolution."""
        video = self._video.get().strip()
        if not video or not os.path.isfile(video):
            messagebox.showwarning("Set region", "Select a video file first.")
            return

        from video_editor import editor_core as ec
        from video_editor import game_vision as gv

        try:
            duration = ec.get_duration(video)
        except Exception:
            duration = 6.0

        frame_path = os.path.join(tempfile.gettempdir(), f"vellum_region_{kind}.png")
        try:
            gv.grab_frame(video, max(0.0, duration / 2), frame_path)
        except Exception as e:
            messagebox.showerror("Set region", f"Could not grab a preview frame:\n{e}")
            return

        try:
            full_img = tk.PhotoImage(file=frame_path)
        except Exception as e:
            messagebox.showerror("Set region", f"Could not load preview frame:\n{e}")
            return

        native_w, native_h = full_img.width(), full_img.height()
        factor = max(1, -(-native_w // 1000))  # shrink big frames so the dialog fits on screen
        img = full_img.subsample(factor, factor) if factor > 1 else full_img

        t = self._t
        win = tk.Toplevel(self)
        win.title(f"Drag a box over the {kind} indicator")
        win.configure(bg=t["bg"])
        win.transient(self.winfo_toplevel())
        win.grab_set()

        tk.Label(
            win, text=f"Click and drag a box tightly around the {kind} indicator, then release.",
            font=("Segoe UI", 10), fg=t["text"], bg=t["bg"],
        ).pack(pady=(12, 8))

        canvas = tk.Canvas(win, width=img.width(), height=img.height(), highlightthickness=0)
        canvas.pack(padx=12, pady=(0, 10))
        canvas.create_image(0, 0, anchor="nw", image=img)
        canvas.image = img  # keep a reference — tkinter won't otherwise

        state = {"rect": None, "x0": 0, "y0": 0}

        def on_press(ev):
            state["x0"], state["y0"] = ev.x, ev.y
            if state["rect"] is not None:
                canvas.delete(state["rect"])
            state["rect"] = canvas.create_rectangle(ev.x, ev.y, ev.x, ev.y, outline="#E11D48", width=2)

        def on_drag(ev):
            canvas.coords(state["rect"], state["x0"], state["y0"], ev.x, ev.y)

        def on_release(ev):
            x0, y0 = state["x0"], state["y0"]
            x1, y1 = ev.x, ev.y
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            if x1 - x0 < 4 or y1 - y0 < 4:
                return  # ignore an accidental click with no real drag

            region = (
                round((x0 * factor) / native_w, 4),
                round((y0 * factor) / native_h, 4),
                round((x1 * factor) / native_w, 4),
                round((y1 * factor) / native_h, 4),
            )

            if kind == "damage":
                self._damage_region = region
                self._damage_status.configure(text="set ✓", fg=t["success"])
            else:
                self._ammo_region = region
                self._ammo_status.configure(text="set ✓", fg=t["success"])

            self._log_line(f"{kind.capitalize()} region set: {region}", "info")
            win.destroy()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)

        ctk.CTkButton(
            win, text="Cancel", command=win.destroy,
            fg_color=t["panel_alt"], hover_color=t["border"],
            text_color=t["text"], font=("Segoe UI", 10),
            height=30, corner_radius=6, width=80,
        ).pack(pady=(0, 12))

    def _browse_video(self):
        path = filedialog.askopenfilename(
            title="Select video file",
            filetypes=[
                ("Video files", "*.mp4 *.mov *.avi *.mkv *.webm *.m4v"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._video.set(path)
            self._log_line(f"Selected: {os.path.basename(path)}", "info")
            self._app.set_status(f"Loaded: {os.path.basename(path)}")

    def _browse_outdir(self):
        path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._outdir.set(path)

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_line(self, text, level="info"):
        """Thread-safe log append."""
        if getattr(self._app, "_verbose", False):
            print(f"[{level.upper()}] {text}")

        def _write():
            self._log.configure(state="normal")
            self._log.insert("end", text + "\n", level)
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _write)

    def _set_progress(self, pct):
        def _upd():
            if pct is None:
                return
            self._progress_var.set(pct / 100.0)
        self.after(0, _upd)

    # ─────────────────────────────────────────────────────────────────────────
    # Processing
    # ─────────────────────────────────────────────────────────────────────────
    def _run(self):
        if self._running:
            return

        video = self._video.get().strip()
        if not video:
            messagebox.showwarning("No file", "Please select a video file first.")
            return
        if not os.path.isfile(video):
            messagebox.showerror("File not found", f"Cannot find:\n{video}")
            return

        self._running = True
        self._run_btn.configure(state="disabled", text="Processing…")
        self._progress.grid()
        self._progress_var.set(0)
        self._log_line("─" * 48, "info")
        self._log_line(f"Starting: {os.path.basename(video)}", "bold")
        self._app.set_status("Processing…", "warning")

        # Run in background thread so UI stays responsive
        thread = threading.Thread(target=self._worker, daemon=True)
        thread.start()

    def _worker(self):
        from video_editor import editor_config as cfg
        from video_editor.editor_core import process_video, check_dependencies

        # Push every setting the pipeline reads off the config module BEFORE
        # calling process_video — analyze() reads these directly, so setting
        # them after the run (as used to happen with USE_GAME_AUDIO) means
        # they silently apply one run too late.
        cfg.USE_GAME_VISION   = self._game_vision.get()
        cfg.GAME_DAMAGE_REGION = self._damage_region
        cfg.GAME_AMMO_REGION   = self._ammo_region
        cfg.VAD_BACKEND         = self._vad_backend.get()
        cfg.SILERO_DEVICE       = self._vad_device.get()
        cfg.SILERO_THRESHOLD    = self._silero_thresh.get()

        ok, err = check_dependencies(cfg.VAD_BACKEND, cfg.SILERO_DEVICE)
        if not ok:
            self._log_line(f"Missing dependencies:\n  {err}", "error")
            self._finish(success=False)
            return

        if cfg.USE_GAME_VISION and not (cfg.GAME_DAMAGE_REGION or cfg.GAME_AMMO_REGION):
            self._log_line(
                "Game HUD detection is on but no region is set — "
                "set a damage or ammo region, or turn the option off.", "warning",
            )

        def progress_cb(pct, msg):
            self._log_line(msg, "info")
            if pct is not None:
                self._set_progress(pct)
            self.after(0, lambda: self._app.set_status(msg, "info"))

        try:
            paths = process_video(
                video_path       = self._video.get().strip(),
                mode             = self._mode.get(),
                output_folder    = self._outdir.get().strip() or None,
                volume_threshold = self._thresh.get(),
                progress_cb      = progress_cb,
            )

            self._log_line(f"✓ Exported {len(paths)} file(s):", "success")
            for p in paths:
                self._log_line(f"  {p}", "success")
            self._finish(success=True)

        except Exception as exc:
            import traceback
            self._log_line(traceback.format_exc(), "error")
            self._finish(success=False, msg=str(exc))

    def _finish(self, success: bool, msg: str = ""):
        def _ui():
            self._running = False
            self._run_btn.configure(state="normal", text="▶  Process Video")
            self._progress.grid_remove()
            if success:
                self._app.set_status("Done — output saved.", "success")
            else:
                short = (msg[:80] + "…") if len(msg) > 80 else msg
                self._app.set_status(f"Error: {short}", "error")
        self.after(0, _ui)
