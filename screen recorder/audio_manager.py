"""
Vellum Screen Capture
Audio device handling (mic + system audio)
"""

import platform


class AudioManager:

    def __init__(self):
        self.system = platform.system()

    # ----------------------------------------
    # Microphone input
    # ----------------------------------------
    def get_mic_input(self):
        if self.system == "Windows":
            # DirectShow — list devices with: ffmpeg -list_devices true -f dshow -i dummy
            return ["-f", "dshow", "-i", "audio=Microphone Array"]

        elif self.system == "Linux":
            # PulseAudio / PipeWire default source
            return ["-f", "pulse", "-i", "default"]

        return []

    # ----------------------------------------
    # System audio input
    # ----------------------------------------
    def get_system_audio_input(self):
        if self.system == "Windows":
            # WASAPI loopback — captures what's playing through speakers
            return ["-f", "wasapi", "-loopback", "1", "-i", "default"]

        elif self.system == "Linux":
            # PulseAudio monitor of default output sink
            return ["-f", "pulse", "-i", "default.monitor"]

        return []
