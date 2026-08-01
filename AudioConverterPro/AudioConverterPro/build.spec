# PyInstaller spec for Audio Converter Pro.
#
# Build on the target OS (PyInstaller doesn't cross-compile):
#   Windows:  pyinstaller build.spec
#   Linux:    pyinstaller build.spec
#
# Both produce a single windowed executable in dist/. ffmpeg is NOT
# bundled by default — it's discovered at runtime (see utils.find_tool).
# To ship ffmpeg alongside the app instead of requiring a system
# install, drop ffmpeg(.exe)/ffprobe(.exe) into an "ffmpeg/" folder
# next to this spec file before building; the block below will
# pick them up automatically.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None
root = Path(SPECPATH)

# customtkinter ships its color/theme JSON as package data — without
# this, a frozen build launches to a blank/unstyled window.
datas = collect_data_files("customtkinter")

# Optionally bundle a local ffmpeg build (see note above).
ffmpeg_dir = root / "ffmpeg"
binaries = []
if ffmpeg_dir.is_dir():
    for exe_name in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
        exe_path = ffmpeg_dir / exe_name
        if exe_path.is_file():
            binaries.append((str(exe_path), "."))

icon = None
if sys.platform.startswith("win"):
    candidate = root / "icon.ico"
    if candidate.is_file():
        icon = str(candidate)
elif sys.platform == "darwin":
    candidate = root / "icon.icns"
    if candidate.is_file():
        icon = str(candidate)

a = Analysis(
    ["main.py"],
    pathex=[str(root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AudioConverterPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # windowed app — no console on Windows or Linux
    disable_windowed_traceback=False,
    icon=icon,
)
