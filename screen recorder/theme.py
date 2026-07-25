"""
Vellum Screen Capture
Theme (colors, fonts, appearance mode)
"""

import platform as _platform

# -------------------------------------------------
# customtkinter appearance
# -------------------------------------------------

APPEARANCE_MODE = "dark"
COLOR_THEME = "blue"

# -------------------------------------------------
# Colors
# -------------------------------------------------

BACKGROUND = "#08192D"
SIDEBAR = "#0C223D"
CARD = "#102B4C"

ACCENT = "#00BFFF"
ACCENT_HOVER = "#28CFFF"

TEXT = "#FFFFFF"
TEXT_SECONDARY = "#A6B6CC"

SUCCESS = "#2ECC71"
WARNING = "#F1C40F"
ERROR = "#E74C3C"

BORDER = "#1D4F80"

# -------------------------------------------------
# Fonts
# -------------------------------------------------

FONT = (
    "Segoe UI" if _platform.system() == "Windows" else
    "SF Pro Text" if _platform.system() == "Darwin" else
    "Ubuntu"  # Linux fallback; tkinter will try DejaVu Sans if absent
)

TITLE_FONT = (FONT, 28, "bold")
HEADER_FONT = (FONT, 20, "bold")
NORMAL_FONT = (FONT, 14)
SMALL_FONT = (FONT, 12)
