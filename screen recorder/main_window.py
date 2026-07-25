"""
Vellum Screen Capture
Main Window
"""

import threading
import time

import customtkinter as ctk

from config import FPS_OPTIONS, QUALITY_OPTIONS, VIDEO_FORMATS, DEFAULT_FPS
from theme import ACCENT, SUCCESS, WARNING, ERROR, SIDEBAR, CARD, BORDER, TEXT_SECONDARY, NORMAL_FONT, SMALL_FONT
from recorder import Recorder
from region_selector import RegionSelector
from widgets import LabeledCombo

PAD_Y = 14  # consistent vertical padding for every control row widget


class MainWindow:

    def __init__(self, master, app):
        self.master = master
        self.app = app
        self.settings = app.settings
        self.recorder = Recorder(app.ffmpeg, self.settings)
        self.is_recording = False
        self.build_layout()

    # ----------------------------
    # Layout
    # ----------------------------
    def build_layout(self):
        # ── Status bar ──────────────────────────────────────────
        status_frame = ctk.CTkFrame(self.master, fg_color=SIDEBAR)
        status_frame.pack(fill="x", padx=12, pady=(12, 0))

        self.status = ctk.CTkLabel(
            status_frame,
            text="Status: Ready",
            font=NORMAL_FONT,
            text_color=SUCCESS,
        )
        self.status.pack(side="left", padx=16, pady=10)

        # ── Controls bar ─────────────────────────────────────────
        controls = ctk.CTkFrame(self.master, fg_color=CARD)
        controls.pack(fill="x", padx=12, pady=8)

        self.fps = LabeledCombo(
            controls, "FPS", [str(v) for v in FPS_OPTIONS],
            width=84, initial=self.settings.get("fps", DEFAULT_FPS),
        )
        self.fps.pack(side="left", padx=16, pady=PAD_Y)

        self.quality = LabeledCombo(
            controls, "Quality", QUALITY_OPTIONS,
            width=110, initial=self.settings.get("quality", "High"),
        )
        self.quality.pack(side="left", padx=16, pady=PAD_Y)

        self.fmt = LabeledCombo(
            controls, "Format", VIDEO_FORMATS,
            width=84, initial=self.settings.get("format", "mp4"),
        )
        self.fmt.pack(side="left", padx=16, pady=PAD_Y)

        self.mic_var = ctk.BooleanVar(value=self.settings.get("microphone", False))
        ctk.CTkCheckBox(
            controls, text="Microphone", variable=self.mic_var, font=SMALL_FONT
        ).pack(side="left", padx=(20, 8), pady=PAD_Y)

        self.sys_audio_var = ctk.BooleanVar(value=self.settings.get("system_audio", False))
        ctk.CTkCheckBox(
            controls, text="System Audio", variable=self.sys_audio_var, font=SMALL_FONT
        ).pack(side="left", padx=(0, 16), pady=PAD_Y)

        # ── Capture area ─────────────────────────────────────────
        # Default is the full virtual desktop (all monitors). Clicking
        # "Select Region" lets the user drag out a single monitor or a
        # custom area instead of always recording everything.
        self.region_btn = ctk.CTkButton(
            controls, text="Select Region", width=120, height=28,
            font=SMALL_FONT, fg_color=CARD, hover_color=SIDEBAR,
            border_width=1, border_color=BORDER,
            command=self._select_region,
        )
        self.region_btn.pack(side="left", padx=(0, 8), pady=PAD_Y)
        # Right-click as a quick way back to full-desktop capture without
        # having to drag a region covering the whole screen.
        self.region_btn.bind("<Button-3>", lambda e: self._reset_region())

        self.region_label = ctk.CTkLabel(
            controls, text=self._region_status_text(), font=SMALL_FONT,
            text_color=TEXT_SECONDARY,
        )
        self.region_label.pack(side="left", padx=(0, 16), pady=PAD_Y)

        # ── Action buttons ───────────────────────────────────────
        btn_frame = ctk.CTkFrame(self.master, fg_color="transparent")
        btn_frame.pack(pady=12)

        self.start_btn = ctk.CTkButton(
            btn_frame,
            text="Start Recording",
            fg_color=ACCENT,
            hover_color="#28CFFF",
            width=160,
            height=40,
            command=self._start_with_countdown,
        )
        self.start_btn.pack(side="left", padx=8)

        self.stop_btn = ctk.CTkButton(
            btn_frame,
            text="Stop",
            fg_color=ERROR,
            width=100,
            height=40,
            state="disabled",
            command=self.stop_recording,
        )
        self.stop_btn.pack(side="left", padx=8)

    # ----------------------------
    # Capture region
    # ----------------------------
    def _region_status_text(self):
        region = self.settings.get("capture_region")
        if not region:
            return "Full Desktop"
        _, _, w, h = region
        return f"Region: {w}x{h} (right-click to reset)"

    def _select_region(self):
        # Hide the main window while dragging out a region so it doesn't
        # cover part of the screen you're trying to select.
        self.master.withdraw()
        self.master.after(150, self._open_region_selector)

    def _open_region_selector(self):
        def on_selected(region):
            self.master.deiconify()
            if region:
                self.settings.set("capture_region", list(region))
            self.region_label.configure(text=self._region_status_text())

        RegionSelector(self.master, on_selected)

    def _reset_region(self):
        self.settings.set("capture_region", None)
        self.region_label.configure(text=self._region_status_text())

    # ----------------------------
    # Start (with countdown)
    # ----------------------------
    def _start_with_countdown(self):
        self.start_btn.configure(state="disabled")
        threading.Thread(target=self._countdown_then_record, daemon=True).start()

    def _countdown_then_record(self):
        countdown = self.settings.get("countdown", 3)
        for i in range(countdown, 0, -1):
            self.status.configure(text=f"Starting in {i}...", text_color=WARNING)
            time.sleep(1)
        self.start_recording()

    def start_recording(self):
        self.settings.set("fps", int(self.fps.get()))
        self.settings.set("quality", self.quality.get())
        self.settings.set("format", self.fmt.get())
        self.settings.set("microphone", self.mic_var.get())
        self.settings.set("system_audio", self.sys_audio_var.get())

        self.is_recording = True
        self.status.configure(text="Status: Recording...", text_color=SUCCESS)
        self.stop_btn.configure(state="normal")
        self.recorder.start()

        # start() may fail immediately (ffmpeg missing, bad command, etc.)
        # without raising - check last_error right away instead of leaving
        # a false "Recording..." status on screen with nothing happening.
        if not self.recorder.is_recording():
            self.is_recording = False
            error = self.recorder.last_error or "Unknown error starting ffmpeg"
            self.status.configure(text=f"Error: {error[:80]}", text_color=ERROR)
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    # ----------------------------
    # Stop recording
    # ----------------------------
    def stop_recording(self):
        self.is_recording = False
        output, error = self.recorder.stop()

        if error:
            self.status.configure(text=f"Error: {error[:80]}", text_color=ERROR)
        elif output:
            self.status.configure(text=f"Saved: {output}", text_color=SUCCESS)
        else:
            self.status.configure(text="Stopped (no output)", text_color=WARNING)

        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
