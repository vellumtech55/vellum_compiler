"""
Audio Converter Pro
Runs ffmpeg conversions.

Improvements over the original:
  - ffmpeg/ffprobe are located once via utils.find_tool() instead of
    assuming "ffmpeg" resolves on PATH (it often doesn't on Windows).
  - No console window flashes on Windows for every file (subprocess
    flags from utils.subprocess_flags()).
  - Real, per-file progress via ffprobe duration + `ffmpeg -progress`,
    reported through an on_progress(fraction) callback, instead of the
    UI just jumping from 0% to 100% per file.
  - Conversions can be cancelled mid-file via a threading.Event.
"""

import subprocess
from pathlib import Path

from utils import subprocess_flags


class ConversionCancelled(Exception):
    pass


def auto_rename(path: Path) -> Path:
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def probe_duration_seconds(ffprobe_path, input_file) -> float | None:
    if not ffprobe_path:
        return None
    cmd = [
        ffprobe_path, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrapper=1:nokey=1",
        str(input_file),
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, **subprocess_flags()
        )
        return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, OSError):
        return None


def convert_file(
    input_file,
    output_folder,
    fmt,
    bitrate,
    sample_rate,
    channels,
    overwrite_mode="auto_rename",
    ffmpeg_path="ffmpeg",
    ffprobe_path=None,
    on_progress=None,
    cancel_event=None,
):
    """
    Returns (success: bool, message: str).
    message is the output path on success, or a human-readable error.
    """
    src = Path(input_file)
    if not src.exists():
        return False, f"File not found: {src}"

    dst = Path(output_folder) / f"{src.stem}.{fmt}"

    if dst.exists():
        if overwrite_mode == "skip":
            return False, "Skipped (file already exists)"
        elif overwrite_mode == "auto_rename":
            dst = auto_rename(dst)
        # "overwrite" falls through — ffmpeg's -y handles it.

    try:
        Path(output_folder).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"Can't write to output folder: {e}"

    duration = probe_duration_seconds(ffprobe_path, src)

    cmd = [
        ffmpeg_path, "-y", "-i", str(src),
        "-b:a", f"{bitrate}k",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-progress", "pipe:1", "-nostats",
        str(dst),
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            **subprocess_flags(),
        )
    except OSError as e:
        return False, f"Couldn't launch ffmpeg: {e}"

    stderr_lines = []
    try:
        for line in process.stdout:
            if cancel_event is not None and cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                if dst.exists():
                    dst.unlink(missing_ok=True)
                return False, "Cancelled"

            line = line.strip()
            if on_progress and duration and line.startswith("out_time_ms="):
                try:
                    out_time_ms = int(line.split("=", 1)[1])
                    fraction = min(1.0, max(0.0, (out_time_ms / 1_000_000) / duration))
                    on_progress(fraction)
                except (ValueError, ZeroDivisionError):
                    pass

        stderr_lines = process.stderr.read().strip().splitlines()
        returncode = process.wait()
    finally:
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    if returncode != 0:
        detail = stderr_lines[-1] if stderr_lines else f"ffmpeg exited with code {returncode}"
        return False, detail

    if on_progress:
        on_progress(1.0)

    return True, str(dst)
