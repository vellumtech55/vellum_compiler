A desktop GUI for batch-converting audio/video files with ffmpeg.
Runs on Windows and Linux (and macOS).

## What changed in this rebuild

- **ffmpeg is auto-detected**, checking PATH, common per-OS install
  locations, and a folder next to the app — instead of assuming
  `ffmpeg` just runs. Missing ffmpeg now shows a clear, OS-specific
  install message rather than failing every conversion silently.
- **Settings are stored in the correct per-user config directory**
  (`%APPDATA%\AudioConverterPro` on Windows, `~/.config/AudioConverterPro`
  on Linux, via `platformdirs`) instead of a relative `config.json`
  that broke depending on the working directory or install location.
- **No console flash on Windows** — every ffmpeg subprocess call is
  launched with the flags needed to keep it silent.
- **Thread-safe UI updates.** Conversion runs on a background thread
  and only ever posts events to a queue that the main thread drains;
  the original called Tk methods directly from the worker thread,
  which is undefined behavior and a common source of Windows-specific
  crashes.
- **Real per-file progress** (via `ffprobe` duration + `ffmpeg
  -progress`), plus a **Cancel** button that stops the current file.
- **Settings are validated** (bitrate/sample rate ranges, valid
  channel count, etc.) with inline errors instead of passing bad
  values straight to ffmpeg.
- Queue and config access are safe to touch from both threads.

## Setup

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/download.html)
installed and on PATH (or see "Bundling ffmpeg" below).

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
python main.py
