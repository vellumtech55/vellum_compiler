"""
Vellum Screen Capture
Audio device handling (mic + system audio)
"""

import platform
import re
import subprocess


class AudioManager:

    # Windows has no native ffmpeg loopback format ("-f wasapi" is not a
    # real ffmpeg input - using it produces a confusing, unrelated-looking
    # "Unrecognized option" error from ffmpeg's argument parser). System
    # audio there has to go through "-f dshow" using whichever loopback
    # capture device the machine happens to expose, most commonly one of
    # these names.
    _LOOPBACK_HINTS = ("stereo mix", "what u hear", "virtual-audio-capturer", "loopback")

    def __init__(self, ffmpeg_path=None):
        self.system = platform.system()
        self.ffmpeg_path = ffmpeg_path
        self.last_error = None
        self._dshow_audio_devices = None  # cached after first list_devices call

    # ----------------------------------------
    # Enumerate real DirectShow audio device names
    # ----------------------------------------
    def _list_dshow_audio_devices(self):
        if self._dshow_audio_devices is not None:
            return self._dshow_audio_devices

        self._dshow_audio_devices = []

        if not self.ffmpeg_path:
            return self._dshow_audio_devices

        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-hide_banner", "-list_devices", "true",
                 "-f", "dshow", "-i", "dummy"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            return self._dshow_audio_devices

        # ffmpeg always "fails" on this call (dummy isn't a real device) -
        # that's expected; the device list itself is what we want, printed
        # to stderr under separate "video devices" / "audio devices" headers.
        in_audio_section = False
        name_re = re.compile(r'"([^"]+)"')

        for line in result.stderr.splitlines():
            if "DirectShow audio devices" in line:
                in_audio_section = True
                continue
            if "DirectShow video devices" in line:
                in_audio_section = False
                continue
            if not in_audio_section or "Alternative name" in line:
                continue

            match = name_re.search(line)
            if match:
                self._dshow_audio_devices.append(match.group(1))

        return self._dshow_audio_devices

    # ----------------------------------------
    # Microphone input
    # ----------------------------------------
    def get_mic_input(self):
        self.last_error = None

        if self.system == "Windows":
            devices = self._list_dshow_audio_devices()
            mic = next(
                (d for d in devices if not any(h in d.lower() for h in self._LOOPBACK_HINTS)),
                None,
            )
            if not mic:
                self.last_error = "No microphone found (checked DirectShow audio devices)"
                return []
            return ["-f", "dshow", "-i", f"audio={mic}"]

        elif self.system == "Linux":
            # PulseAudio / PipeWire default source
            return ["-f", "pulse", "-i", "default"]

        return []

    # ----------------------------------------
    # System audio input
    # ----------------------------------------
    def get_system_audio_input(self):
        self.last_error = None

        if self.system == "Windows":
            devices = self._list_dshow_audio_devices()
            loopback = next(
                (d for d in devices if any(h in d.lower() for h in self._LOOPBACK_HINTS)),
                None,
            )
            if not loopback:
                self.last_error = (
                    "No system-audio loopback device found - enable "
                    "'Stereo Mix' in Windows Sound settings (Recording tab, "
                    "right-click > Show Disabled Devices) or install a "
                    "virtual audio cable"
                )
                return []
            return ["-f", "dshow", "-i", f"audio={loopback}"]

        elif self.system == "Linux":
            # PulseAudio monitor of default output sink
            return ["-f", "pulse", "-i", "default.monitor"]

        return []
