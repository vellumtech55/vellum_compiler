"""
Audio Converter Pro
Settings tab UI.

Owns no persistence itself — it hands values back to whoever
constructed it via the on_save callback, and the app decides what to
do with them (main.py calls settings_manager.save_settings). Values
are validated here before on_save is ever called, with the specific
problem shown inline instead of letting bad settings reach ffmpeg.
"""

import customtkinter as ctk

from settings_manager import validate_settings

FORMATS = ["mp3", "wav", "flac", "aac", "ogg", "m4a"]
OVERWRITE_MODES = ["auto_rename", "skip", "overwrite"]


class SettingsTab(ctk.CTkFrame):

    def __init__(self, parent, settings, on_save, accent_color="#00BFFF"):
        super().__init__(parent, fg_color="transparent")
        self.on_save = on_save

        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(expand=True, padx=40, pady=20)

        def row(label, widget_fn):
            ctk.CTkLabel(wrap, text=label, anchor="w").pack(fill="x", pady=(12, 2))
            widget = widget_fn(wrap)
            widget.pack(fill="x")
            return widget

        self.format_box = row("Output Format", lambda p: ctk.CTkComboBox(p, values=FORMATS))
        self.format_box.set(settings["output_format"])

        self.bitrate_entry = row("Bitrate (kbps)", lambda p: ctk.CTkEntry(p))
        self.bitrate_entry.insert(0, settings["bitrate"])

        self.sample_rate_entry = row("Sample Rate (Hz)", lambda p: ctk.CTkEntry(p))
        self.sample_rate_entry.insert(0, settings["sample_rate"])

        self.channels_entry = row(
            "Channels (1 = mono, 2 = stereo)", lambda p: ctk.CTkComboBox(p, values=["1", "2"])
        )
        self.channels_entry.set(settings["channels"])

        self.overwrite_box = row(
            "If file already exists",
            lambda p: ctk.CTkComboBox(p, values=OVERWRITE_MODES),
        )
        self.overwrite_box.set(settings["overwrite_mode"])

        self.error_label = ctk.CTkLabel(wrap, text="", text_color="#FF6B6B", wraplength=380, justify="left")
        self.error_label.pack(fill="x", pady=(16, 0))

        ctk.CTkButton(
            wrap, text="Save Settings", fg_color=accent_color, command=self._save
        ).pack(pady=(8, 24))

    def get_values(self):
        return {
            "output_format": self.format_box.get().strip().lower(),
            "bitrate": self.bitrate_entry.get().strip(),
            "sample_rate": self.sample_rate_entry.get().strip(),
            "channels": self.channels_entry.get().strip(),
            "overwrite_mode": self.overwrite_box.get().strip(),
        }

    def _save(self):
        values = self.get_values()
        ok, errors = validate_settings(values)
        if not ok:
            self.error_label.configure(text="  •  ".join(errors.values()))
            return
        self.error_label.configure(text="")
        self.on_save(values)
