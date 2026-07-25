"""
Vellum Screen Capture
Configuration
"""

import sys
from pathlib import Path

# -------------------------------------------------
# Application
# -------------------------------------------------

APP_NAME = "Vellum Screen Capture"
APP_VERSION = "1.0.0"
WINDOW_SIZE = "1000x700"

# -------------------------------------------------
# Recording
# -------------------------------------------------

DEFAULT_FPS = 60

FPS_OPTIONS = [30, 60, 120]

QUALITY_OPTIONS = ["Low", "Medium", "High", "Ultra"]

VIDEO_FORMATS = ["mp4", "mkv"]

DEFAULT_FORMAT = "mp4"

# -------------------------------------------------
# Directories
# -------------------------------------------------
#
# IMPORTANT: In a PyInstaller --onefile build, __file__ resolves to the
# temporary extraction folder (sys._MEIPASS), which is wiped after every
# run. If we base ROOT_DIR on __file__, settings.json, recordings/, and
# the ffmpeg/ folder all silently reset or disappear between launches.
#
# Instead, when frozen, base ROOT_DIR on the actual .exe's location
# (sys.executable) so settings/recordings persist next to the exe like
# a normal desktop app.

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent

ASSETS_DIR = ROOT_DIR / "assets"
RECORDINGS_DIR = ROOT_DIR / "recordings"
SETTINGS_FILE = ROOT_DIR / "settings.json"
FFMPEG_FOLDER = ROOT_DIR / "ffmpeg"

# -------------------------------------------------
# FFmpeg
# -------------------------------------------------

WINDOWS_FFMPEG = FFMPEG_FOLDER / "ffmpeg.exe"
LINUX_FFMPEG = "ffmpeg"

# -------------------------------------------------
# Defaults
# -------------------------------------------------

DEFAULT_SETTINGS = {
    "fps": DEFAULT_FPS,
    "quality": "High",
    "format": DEFAULT_FORMAT,
    "microphone": False,
    "system_audio": False,
    "output_folder": str(RECORDINGS_DIR),
    "countdown": 3,
    "hardware_encoder": True,
}
