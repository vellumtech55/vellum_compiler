"""
Audio Converter Pro
Settings persistence.

Config lives in the OS-appropriate per-user config directory instead of
a relative "config.json" next to the script — the old approach broke as
soon as the app was launched from a different working directory, or
installed anywhere the user's account can't write (Program Files,
/usr/bin, etc). platformdirs resolves to:
  Windows:  %APPDATA%\\AudioConverterPro\\config.json
  macOS:    ~/Library/Application Support/AudioConverterPro/config.json
  Linux:    ~/.config/AudioConverterPro/config.json
"""

import json
import tempfile
from pathlib import Path

from platformdirs import user_config_dir

APP_NAME = "AudioConverterPro"
CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "output_format": "mp3",
    "bitrate": "320",
    "sample_rate": "44100",
    "channels": "2",
    "overwrite_mode": "auto_rename",
}

VALID_FORMATS = {"mp3", "wav", "flac", "aac", "ogg", "m4a"}
VALID_OVERWRITE_MODES = {"auto_rename", "skip", "overwrite"}
VALID_CHANNELS = {"1", "2"}


def load_settings() -> dict:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            merged = {**DEFAULTS, **data}
            ok, _ = validate_settings(merged)
            return merged if ok else DEFAULTS.copy()
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass
    return DEFAULTS.copy()


def save_settings(settings: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Write atomically: build the file fully on disk before it replaces
    # the real config, so a crash or power loss mid-write can't leave a
    # truncated/corrupt config.json behind.
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        Path(tmp_path).replace(CONFIG_FILE)
    except OSError:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def validate_settings(settings: dict):
    """Returns (is_valid, {field: error_message})."""
    errors = {}

    fmt = str(settings.get("output_format", "")).lower()
    if fmt not in VALID_FORMATS:
        errors["output_format"] = f"Format must be one of {', '.join(sorted(VALID_FORMATS))}"

    bitrate = str(settings.get("bitrate", ""))
    if not bitrate.isdigit() or not (32 <= int(bitrate) <= 320):
        errors["bitrate"] = "Bitrate must be a number between 32 and 320 (kbps)"

    sample_rate = str(settings.get("sample_rate", ""))
    if not sample_rate.isdigit() or not (8000 <= int(sample_rate) <= 192000):
        errors["sample_rate"] = "Sample rate must be a number between 8000 and 192000 (Hz)"

    channels = str(settings.get("channels", ""))
    if channels not in VALID_CHANNELS:
        errors["channels"] = "Channels must be 1 (mono) or 2 (stereo)"

    overwrite_mode = str(settings.get("overwrite_mode", ""))
    if overwrite_mode not in VALID_OVERWRITE_MODES:
        errors["overwrite_mode"] = f"Must be one of {', '.join(sorted(VALID_OVERWRITE_MODES))}"

    return (len(errors) == 0), errors
