"""
Vellum Screen Capture
Settings Manager
"""

import json
from pathlib import Path

from config import SETTINGS_FILE, DEFAULT_SETTINGS


class Settings:

    def __init__(self):
        self.file = Path(SETTINGS_FILE)
        self.data = {}
        self.load()

    # ----------------------------
    # Load Settings
    # ----------------------------
    def load(self):
        if not self.file.exists():
            self.data = DEFAULT_SETTINGS.copy()
            self.save()
            return

        try:
            with open(self.file, "r", encoding="utf-8") as f:
                self.data = json.load(f)

        except Exception:
            self.data = DEFAULT_SETTINGS.copy()
            self.save()

        # Add any new settings that didn't exist in an older version
        updated = False

        for key, value in DEFAULT_SETTINGS.items():
            if key not in self.data:
                self.data[key] = value
                updated = True

        if updated:
            self.save()

    # ----------------------------
    # Save Settings
    # ----------------------------
    def save(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)

        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    # ----------------------------
    # Get
    # ----------------------------
    def get(self, key, default=None):
        return self.data.get(key, default)

    # ----------------------------
    # Set
    # ----------------------------
    def set(self, key, value):
        self.data[key] = value
        self.save()

    # ----------------------------
    # Reset
    # ----------------------------
    def reset(self):
        self.data = DEFAULT_SETTINGS.copy()
        self.save()

    # ----------------------------
    # Dictionary
    # ----------------------------
    def as_dict(self):
        return self.data
