"""
Vellum Screen Capture
Screen region selector (drag box)
"""

import platform
import tkinter as tk


def get_virtual_desktop_bounds():
    """Return (x, y, width, height) of the full desktop across all monitors.

    Origin (x, y) can be negative - e.g. a second monitor positioned to
    the left of or above the primary one. Callers must treat (x, y) as
    the coordinate-system origin, not assume (0, 0).
    """
    system = platform.system()

    if system == "Windows":
        import ctypes
        user32 = ctypes.windll.user32
        # SM_XVIRTUALSCREEN=76, SM_YVIRTUALSCREEN=77,
        # SM_CXVIRTUALSCREEN=78, SM_CYVIRTUALSCREEN=79
        x = user32.GetSystemMetrics(76)
        y = user32.GetSystemMetrics(77)
        w = user32.GetSystemMetrics(78)
        h = user32.GetSystemMetrics(79)
        return x, y, w, h

    # Linux (X11 with a joined screen via xrandr) and macOS: fall back to
    # what Tk itself reports. This covers the common multi-monitor X11
    # setup but won't span monitors that are on separate X screens.
    probe = tk.Tk()
    probe.withdraw()
    w = probe.winfo_screenwidth()
    h = probe.winfo_screenheight()
    probe.destroy()
    return 0, 0, w, h


class RegionSelector(tk.Toplevel):
    """Full-virtual-desktop overlay for dragging out a capture region.

    Runs as a Toplevel of the app's existing root window rather than a
    second independent Tk() instance, which is unsafe to mix with the
    already-running customtkinter mainloop.

    `callback` is invoked with (x, y, width, height) in the same
    coordinate space as get_virtual_desktop_bounds() - i.e. relative to
    the virtual desktop's own origin, which is what ffmpeg's crop filter
    needs since it operates on the full captured frame.
    """

    def __init__(self, master, callback):
        super().__init__(master)
        self.callback = callback
        self.start_x = None
        self.start_y = None
        self.rect = None

        self.vx, self.vy, self.vw, self.vh = get_virtual_desktop_bounds()

        self.overrideredirect(True)
        self.geometry(f"{self.vw}x{self.vh}+{self.vx}+{self.vy}")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.3)
        self.configure(bg="black")

        self.canvas = tk.Canvas(self, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", self.on_cancel)

        self.focus_force()
        self.grab_set()

    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="red", width=2,
        )

    def on_drag(self, event):
        if self.rect is not None:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1 = min(self.start_x, event.x)
        y1 = min(self.start_y, event.y)
        x2 = max(self.start_x, event.x)
        y2 = max(self.start_y, event.y)

        self.grab_release()
        self.destroy()

        width, height = x2 - x1, y2 - y1
        if width < 4 or height < 4:
            self.callback(None)  # accidental click/tiny drag - no selection
            return

        # Canvas coords are already relative to this window's top-left,
        # which we positioned at the virtual desktop's own origin - so
        # no further offset math is needed here.
        self.callback((x1, y1, width, height))

    def on_cancel(self, event=None):
        self.grab_release()
        self.destroy()
        self.callback(None)
