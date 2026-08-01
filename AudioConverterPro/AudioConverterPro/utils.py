"""
Audio Converter Pro
Cross-platform helpers: resource paths, ffmpeg/ffprobe discovery, and
subprocess flags that keep Windows from flashing a console window.
"""

import shutil
import subprocess
import sys
from pathlib import Path

SUPPORTED = {
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".aiff",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".wmv", ".m4v",
}

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"


def is_supported(path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED


def app_base_dir() -> Path:
    """
    Directory the app is running from — works both for a normal
    python invocation and for a PyInstaller-frozen executable
    (onefile or onedir).
    """
    if getattr(sys, "frozen", False):
        # PyInstaller onefile extracts to sys._MEIPASS at runtime, but the
        # actual .exe/binary (and anything placed next to it, like a
        # bundled ffmpeg) lives next to sys.executable.
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    """Resolve a bundled resource, whether running from source or frozen."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / relative_path
    return Path(__file__).resolve().parent / relative_path


def _candidate_names(tool: str):
    return [f"{tool}.exe", tool] if IS_WINDOWS else [tool]


def _find_bundled(tool: str):
    """Look next to the executable / in an adjacent 'ffmpeg' folder."""
    base = app_base_dir()
    search_dirs = [base, base / "ffmpeg", base / "bin"]
    for d in search_dirs:
        for name in _candidate_names(tool):
            candidate = d / name
            if candidate.is_file():
                return str(candidate)
    return None


def _common_install_locations(tool: str):
    if IS_WINDOWS:
        return [
            Path(r"C:\ffmpeg\bin") / f"{tool}.exe",
            Path(r"C:\Program Files\ffmpeg\bin") / f"{tool}.exe",
            Path(r"C:\Program Files (x86)\ffmpeg\bin") / f"{tool}.exe",
        ]
    if IS_MACOS:
        return [
            Path("/opt/homebrew/bin") / tool,
            Path("/usr/local/bin") / tool,
        ]
    return [
        Path("/usr/bin") / tool,
        Path("/usr/local/bin") / tool,
        Path("/snap/bin") / tool,
    ]


def find_tool(tool: str):
    """
    Locate ffmpeg/ffprobe across Windows, macOS and Linux:
    1. A copy bundled next to the app (for packaged builds).
    2. Whatever's on PATH.
    3. Common per-OS install locations, as a fallback for machines
       where ffmpeg was installed but never added to PATH.
    Returns a path string, or None if nothing was found.
    """
    bundled = _find_bundled(tool)
    if bundled:
        return bundled

    on_path = shutil.which(tool)
    if on_path:
        return on_path

    for candidate in _common_install_locations(tool):
        if candidate.is_file():
            return str(candidate)

    return None


def get_ffmpeg_path():
    return find_tool("ffmpeg")


def get_ffprobe_path():
    return find_tool("ffprobe")


def install_instructions() -> str:
    if IS_WINDOWS:
        return (
            "ffmpeg was not found.\n\n"
            "Install it with 'winget install ffmpeg' (Windows 10/11), "
            "or download a build from https://www.gyan.dev/ffmpeg/builds/ "
            "and add its 'bin' folder to your PATH."
        )
    if IS_MACOS:
        return "ffmpeg was not found.\n\nInstall it with: brew install ffmpeg"
    return (
        "ffmpeg was not found.\n\n"
        "Install it with your package manager, e.g.:\n"
        "  sudo apt install ffmpeg      (Debian/Ubuntu)\n"
        "  sudo dnf install ffmpeg      (Fedora)\n"
        "  sudo pacman -S ffmpeg        (Arch)"
    )


def subprocess_flags() -> dict:
    """
    Extra kwargs for subprocess.Popen/run so ffmpeg doesn't pop up a
    console window on Windows. A no-op on macOS/Linux.
    """
    if not IS_WINDOWS:
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
