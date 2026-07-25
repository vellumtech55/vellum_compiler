"""
Vellum Screen Capture
Main Entry Point
"""

import sys
import traceback
from pathlib import Path


def _log_path():
    # Log next to the exe (or next to main.py in dev) so it's easy to find
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    return base / "crash_log.txt"


def main():
    from app import ScreenCaptureApp
    app = ScreenCaptureApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # --windowed builds have no console, so an uncaught exception here
        # would otherwise just make the app vanish with zero feedback.
        # Write the full traceback to a log file beside the exe instead.
        crash_log = _log_path()
        with open(crash_log, "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
