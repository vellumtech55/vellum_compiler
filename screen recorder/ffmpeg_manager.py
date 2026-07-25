"""
Vellum Screen Capture
FFmpeg Manager
"""

import platform
import shutil
import subprocess
from pathlib import Path

from config import WINDOWS_FFMPEG, LINUX_FFMPEG


class FFmpegManager:

    def __init__(self, settings):
        self.settings = settings
        self.process = None
        self.ffmpeg_path = self.find_ffmpeg()
        self.vaapi_device = self._find_vaapi_device()

    # ----------------------------------------
    # Locate FFmpeg
    # ----------------------------------------
    def find_ffmpeg(self):
        system = platform.system()

        if system == "Windows":
            if Path(WINDOWS_FFMPEG).exists():
                return str(WINDOWS_FFMPEG)

        path = shutil.which(LINUX_FFMPEG)

        if path:
            return path

        return None

    # ----------------------------------------
    # Installed?
    # ----------------------------------------
    def is_installed(self):
        return self.ffmpeg_path is not None

    # ----------------------------------------
    # Version
    # ----------------------------------------
    def get_version(self):
        if not self.is_installed():
            return "Not Installed"

        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
            )
            return result.stdout.splitlines()[0]

        except Exception:
            return "Unknown"

    # ----------------------------------------
    # Available Encoders (compiled into this ffmpeg build)
    # ----------------------------------------
    def get_encoders(self):
        if not self.is_installed():
            return []

        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-encoders"],
                capture_output=True,
                text=True,
            )

            encoders = []

            for line in result.stdout.splitlines():
                if "libx264" in line:
                    encoders.append("libx264")

                if "h264_nvenc" in line:
                    encoders.append("h264_nvenc")

                if "h264_vaapi" in line:
                    encoders.append("h264_vaapi")

                if "h264_amf" in line:
                    encoders.append("h264_amf")

                if "hevc_nvenc" in line:
                    encoders.append("hevc_nvenc")

            return encoders

        except Exception:
            return []

    # ----------------------------------------
    # Find a real VAAPI render node
    # ----------------------------------------
    def _find_vaapi_device(self):
        render_dir = Path("/dev/dri")

        if not render_dir.exists():
            return None

        nodes = sorted(render_dir.glob("renderD*"))

        return str(nodes[0]) if nodes else None

    # ----------------------------------------
    # Actually test an encoder, not just check it's compiled in.
    # `ffmpeg -encoders` only proves the codec was built into the binary;
    # it says nothing about whether the driver/hardware on THIS machine
    # can actually use it. Running a 1-frame throwaway encode is the only
    # reliable way to know it will really work.
    # ----------------------------------------
    def _test_encoder(self, encoder):
        if not self.is_installed():
            return False

        if encoder == "h264_vaapi" and not self.vaapi_device:
            return False

        cmd = [self.ffmpeg_path, "-y", "-f", "lavfi", "-i", "color=black:s=64x64:d=0.1"]

        if encoder == "h264_vaapi":
            cmd += [
                "-vaapi_device", self.vaapi_device,
                "-vf", "format=nv12,hwupload",
                "-c:v", "h264_vaapi",
            ]
        else:
            cmd += ["-c:v", encoder]

        cmd += ["-frames:v", "1", "-f", "null", "-"]

        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            return result.returncode == 0

        except Exception:
            return False

    # ----------------------------------------
    # Choose Best Encoder (probe candidates in priority order)
    # ----------------------------------------
    def get_best_encoder(self):
        encoders = self.get_encoders()

        for candidate in ("h264_nvenc", "h264_vaapi", "h264_amf"):
            if candidate in encoders and self._test_encoder(candidate):
                return candidate

        if "libx264" in encoders:
            return "libx264"

        return "mpeg4"

    # ----------------------------------------
    # Running?
    # ----------------------------------------
    def is_recording(self):
        return self.process is not None

    # ----------------------------------------
    # Stop Recording
    # ----------------------------------------
    def stop(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
