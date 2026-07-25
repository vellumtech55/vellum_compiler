"""
Vellum Screen Capture
Recorder Engine (FFmpeg wrapper)
"""

import os
import signal
import subprocess
import platform
import time
from datetime import datetime

from config import RECORDINGS_DIR
from audio_manager import AudioManager


class Recorder:

    def __init__(self, ffmpeg_manager, settings):
        self.ffmpeg = ffmpeg_manager
        self.settings = settings
        self.audio = AudioManager()
        self.process = None
        self.output_file = None
        self.last_error = None

    # ----------------------------------------
    # Build output filename
    # ----------------------------------------

    def build_output_path(self):
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        fmt = self.settings.get("format", "mp4")
        return str(RECORDINGS_DIR / f"recording_{timestamp}.{fmt}")

    # ----------------------------------------
    # Detect display server (Linux)
    # ----------------------------------------

    @staticmethod
    def _is_wayland():
        return (
            os.environ.get("WAYLAND_DISPLAY") is not None
            or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
        )

    # ----------------------------------------
    # Build FFmpeg command
    # ----------------------------------------

    def build_command(self):
        system = platform.system()
        quality = self.settings.get("quality", "High")
        fps = self.settings.get("fps", 60)
        use_hw = self.settings.get("hardware_encoder", True)

        # --- Screen input ---
        if system == "Windows":
            screen_input = [
                "-f", "gdigrab",
                "-framerate", str(fps),
                "-i", "desktop",
            ]

        elif system == "Darwin":
            screen_input = [
                "-f", "avfoundation",
                "-framerate", str(fps),
                "-i", "1:none",
            ]

        else:  # Linux
            if self._is_wayland():
                screen_input = [
                    "-f", "pipewire",
                    "-framerate", str(fps),
                    "-i", "0",
                ]
            else:
                display = os.environ.get("DISPLAY", ":0.0")
                screen_input = [
                    "-f", "x11grab",
                    "-framerate", str(fps),
                    "-i", display,
                ]

        # --- Audio inputs ---
        audio_inputs = []
        if self.settings.get("microphone", False):
            audio_inputs += self.audio.get_mic_input()
        if self.settings.get("system_audio", False):
            audio_inputs += self.audio.get_system_audio_input()

        # Mix multiple audio streams into one track when both are active
        audio_filter = []
        num_audio = sum([
            bool(self.settings.get("microphone", False)),
            bool(self.settings.get("system_audio", False)),
        ])
        if num_audio > 1:
            audio_filter = [
                "-filter_complex", f"amix=inputs={num_audio}:duration=first",
            ]

        # --- Capture region (monitor/area selection) ---
        # By default ffmpeg captures the full virtual desktop (all
        # monitors combined). If the user dragged out a specific region
        # with RegionSelector, crop the captured frame down to just that
        # area before encoding, instead of always sending the whole
        # multi-monitor frame to the encoder.
        region = self.settings.get("capture_region")
        crop_filter = None
        if region:
            rx, ry, rw, rh = region
            crop_filter = f"crop={rw}:{rh}:{rx}:{ry}"

        # --- Encoder & quality ---
        encoder = self.ffmpeg.get_best_encoder() if use_hw else "libx264"

        quality_map = {
            "Ultra":  ("ultrafast", "18"),
            "High":   ("veryfast",  "23"),
            "Medium": ("fast",      "28"),
            "Low":    ("ultrafast", "32"),
        }

        if encoder == "libx264":
            preset, crf = quality_map.get(quality, ("veryfast", "23"))
            video_settings = [
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", crf,
                "-pix_fmt", "yuv420p",  # required for broad player compatibility
            ]
            if crop_filter:
                video_settings = ["-vf", crop_filter] + video_settings

        elif encoder == "h264_vaapi":
            qp_map = {"Ultra": "18", "High": "23", "Medium": "28", "Low": "34"}
            vaapi_filter = "format=nv12,hwupload"
            if crop_filter:
                vaapi_filter = f"{crop_filter},{vaapi_filter}"
            video_settings = [
                "-vaapi_device", self.ffmpeg.vaapi_device,
                "-vf", vaapi_filter,
                "-c:v", "h264_vaapi",
                "-qp", qp_map.get(quality, "23"),
                # no -pix_fmt: hwupload sets it
            ]

        elif encoder in ("h264_nvenc", "hevc_nvenc"):
            cq_map = {"Ultra": "18", "High": "23", "Medium": "28", "Low": "34"}
            video_settings = [
                "-c:v", encoder,
                "-preset", "p4",
                "-rc", "vbr",
                "-cq", cq_map.get(quality, "23"),
                "-pix_fmt", "yuv420p",
            ]
            if crop_filter:
                video_settings = ["-vf", crop_filter] + video_settings

        elif encoder == "h264_amf":
            video_settings = [
                "-c:v", "h264_amf",
                "-quality", "balanced",
                "-pix_fmt", "yuv420p",
            ]
            if crop_filter:
                video_settings = ["-vf", crop_filter] + video_settings

        else:
            video_settings = ["-c:v", encoder, "-pix_fmt", "yuv420p"]
            if crop_filter:
                video_settings = ["-vf", crop_filter] + video_settings

        return [
            self.ffmpeg.ffmpeg_path,
            "-y",              # overwrite output without asking
            *screen_input,
            *audio_inputs,
            *audio_filter,
            *video_settings,
            self.output_file,
        ]

    # ----------------------------------------
    # Pull the real failure reason out of ffmpeg's stderr
    # ----------------------------------------
    # ffmpeg always writes its version/build banner and config lines
    # first - those are not errors. The actual reason it exited (bad
    # device name, invalid argument, etc.) is near the end of the output.
    @staticmethod
    def _extract_error(stderr_bytes):
        text = stderr_bytes.decode(errors="replace").strip()
        if not text:
            return None

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            return None

        noise_prefixes = ("ffmpeg version", "built with", "configuration:", "lib")
        meaningful = [ln for ln in lines if not ln.lower().startswith(noise_prefixes)]

        return (meaningful or lines)[-1]

    # ----------------------------------------
    # Start recording
    # ----------------------------------------

    def start(self):
        self.last_error = None

        if not self.ffmpeg.is_installed():
            self.last_error = "ffmpeg not found (not on PATH and not bundled next to the app)"
            return

        self.output_file = self.build_output_path()
        cmd = self.build_command()

        # On Windows this app runs windowed (no console - see main.py), so
        # GenerateConsoleCtrlEvent has no console to route through and
        # raises "[WinError 6] The handle is invalid" if we try to signal
        # the child. We stop ffmpeg via its stdin 'q' command instead (see
        # stop()), which works regardless of whether we have a console, so
        # no special creationflags are needed here.
        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,      # used to send 'q' for a clean stop
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,     # capture for error reporting
            )
        except Exception as e:
            self.process = None
            self.last_error = f"Failed to launch ffmpeg: {e}"
            return

        # Bad audio device names, invalid resolutions, etc. make ffmpeg
        # exit almost immediately. Without this check, is_recording()
        # would still report True (the Popen object exists) even though
        # nothing is actually being recorded, and the real error wouldn't
        # surface until the user clicked Stop.
        time.sleep(0.4)
        if self.process.poll() is not None:
            _, stderr_bytes = self.process.communicate()
            self.last_error = self._extract_error(stderr_bytes) or "ffmpeg exited immediately"
            self.process = None

    # ----------------------------------------
    # Stop recording
    # ----------------------------------------

    def is_recording(self):
        return self.process is not None

    def stop(self):
        if not self.process:
            # Recording never actually started (e.g. ffmpeg missing or
            # failed to launch) - surface the real reason instead of
            # silently returning nothing.
            return None, self.last_error or "Recording never started"

        try:
            # Ask ffmpeg to finalize the container cleanly rather than
            # hard-killing it. A forceful kill (taskkill /F, terminate())
            # cuts ffmpeg off mid-write and leaves the output file with no
            # valid index/moov atom - the file is left corrupted even
            # though the app reports success.
            if platform.system() == "Windows":
                # No console is available to send CTRL_BREAK_EVENT through
                # (this app runs windowed), so use ffmpeg's own graceful-quit
                # keystroke on stdin instead - works with no console needed.
                try:
                    self.process.stdin.write(b"q")
                    self.process.stdin.flush()
                except (OSError, ValueError):
                    pass  # pipe already closed - fall through to communicate()
            else:
                self.process.send_signal(signal.SIGINT)

            _, stderr_bytes = self.process.communicate(timeout=10)

            # 255 / -2 are normal ffmpeg exit codes after SIGINT on POSIX;
            # Windows returns 0 after a clean 'q' stdin quit.
            if self.process.returncode not in (0, 255, -2):
                self.last_error = self._extract_error(stderr_bytes)

        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
            self.last_error = "ffmpeg did not stop in time and was force-killed"

        except Exception as e:
            self.last_error = str(e)

        finally:
            self.process = None

        return self.output_file, self.last_error
