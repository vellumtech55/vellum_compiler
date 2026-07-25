"""
Vellum Screen Capture
Global hotkeys (F8 start/stop)
"""

import threading

import keyboard


class Hotkeys:

    def __init__(self, app):
        self.app = app
        self.recording = False

    def start(self):
        def loop():
            keyboard.add_hotkey("F8", self.toggle_recording)
            keyboard.wait()

        t = threading.Thread(target=loop, daemon=True)
        t.start()

    def toggle_recording(self):
        if self.app.main_window.is_recording:
            self.app.main_window.stop_recording()
        else:
            self.app.main_window.start_recording()
