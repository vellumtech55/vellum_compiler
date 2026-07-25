"""
Vellum Screen Capture
Application Controller
"""

import customtkinter as ctk

from config import APP_NAME, WINDOW_SIZE
from theme import APPEARANCE_MODE, COLOR_THEME, BACKGROUND
from settings import Settings
from ffmpeg_manager import FFmpegManager
from hotkeys import Hotkeys
from main_window import MainWindow


class ScreenCaptureApp:

    def __init__(self):
        # Appearance
        ctk.set_appearance_mode(APPEARANCE_MODE)
        ctk.set_default_color_theme(COLOR_THEME)

        # Main window
        self.root = ctk.CTk()
        self.root.title(APP_NAME)
        self.root.geometry(WINDOW_SIZE)
        self.root.minsize(900, 650)
        self.root.configure(fg_color=BACKGROUND)

        # Settings
        self.settings = Settings()

        # FFmpeg
        self.ffmpeg = FFmpegManager(self.settings)

        # Hotkeys (after root window exists)
        self.hotkeys = Hotkeys(self)
        self.hotkeys.start()

        # Main UI
        self.main_window = MainWindow(master=self.root, app=self)

    def run(self):
        self.root.mainloop()
