import os
import shutil
import threading
import customtkinter as ctk
from tkinter import filedialog

FILE_TYPES = {
    "Images": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv"],
    "Music": [".mp3", ".wav", ".flac"],
    "Documents": [".pdf", ".docx", ".txt", ".pptx", ".xlsx"]
}

# ---- Theme: black / gray / blue ----
BG_COLOR = "#0d0d0d"
PANEL_COLOR = "#1a1a1a"
GRAY = "#2b2b2b"
GRAY_LIGHT = "#3d3d3d"
BLUE = "#2f7dd6"
BLUE_HOVER = "#255fa8"
TEXT_COLOR = "#e6e6e6"
SUBTEXT_COLOR = "#9aa0a6"

ctk.set_appearance_mode("dark")


class OrganizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("File Organizer")
        self.geometry("620x520")
        self.minsize(560, 460)
        self.configure(fg_color=BG_COLOR)

        self.source_dir = ctk.StringVar(value=os.path.expanduser("~/Downloads"))
        self.is_running = False

        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 8))

        ctk.CTkLabel(
            header, text="File Organizer",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=TEXT_COLOR
        ).pack(anchor="w")

        ctk.CTkLabel(
            header, text="Sort files into folders by type",
            font=ctk.CTkFont(size=13),
            text_color=SUBTEXT_COLOR
        ).pack(anchor="w", pady=(2, 0))

        # Folder picker
        folder_frame = ctk.CTkFrame(self, fg_color=PANEL_COLOR, corner_radius=10)
        folder_frame.pack(fill="x", padx=24, pady=12)

        ctk.CTkLabel(
            folder_frame, text="Source Folder", text_color=SUBTEXT_COLOR,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=16, pady=(12, 0))

        path_row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        path_row.pack(fill="x", padx=16, pady=(4, 16))

        self.path_entry = ctk.CTkEntry(
            path_row, textvariable=self.source_dir,
            fg_color=GRAY, border_color=GRAY_LIGHT, border_width=1,
            text_color=TEXT_COLOR
        )
        self.path_entry.pack(side="left", fill="x", expand=True, ipady=4)

        ctk.CTkButton(
            path_row, text="Browse", width=90,
            fg_color=GRAY_LIGHT, hover_color=GRAY, text_color=TEXT_COLOR,
            command=self.browse_folder
        ).pack(side="left", padx=(8, 0))

        # File type categories preview
        cat_frame = ctk.CTkFrame(self, fg_color=PANEL_COLOR, corner_radius=10)
        cat_frame.pack(fill="x", padx=24, pady=(0, 12))

        ctk.CTkLabel(
            cat_frame, text="Categories", text_color=SUBTEXT_COLOR,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=16, pady=(12, 4))

        cats_text = "  ".join(
            f"{name} ({', '.join(exts)})" for name, exts in FILE_TYPES.items()
        )
        ctk.CTkLabel(
            cat_frame, text=cats_text + "   Other (everything else)",
            text_color=TEXT_COLOR, font=ctk.CTkFont(size=11),
            wraplength=540, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # Run button + progress
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=24, pady=(0, 8))

        self.run_button = ctk.CTkButton(
            action_frame, text="Organize Files", height=40,
            fg_color=BLUE, hover_color=BLUE_HOVER, text_color="#ffffff",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.start_organize
        )
        self.run_button.pack(fill="x")

        self.progress_bar = ctk.CTkProgressBar(
            action_frame, progress_color=BLUE, fg_color=GRAY
        )
        self.progress_bar.pack(fill="x", pady=(10, 0))
        self.progress_bar.set(0)

        # Log output
        log_frame = ctk.CTkFrame(self, fg_color=PANEL_COLOR, corner_radius=10)
        log_frame.pack(fill="both", expand=True, padx=24, pady=(12, 24))

        ctk.CTkLabel(
            log_frame, text="Activity Log", text_color=SUBTEXT_COLOR,
            font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=16, pady=(12, 4))

        self.log_box = ctk.CTkTextbox(
            log_frame, fg_color=GRAY, text_color=TEXT_COLOR,
            border_width=0, wrap="word"
        )
        self.log_box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def browse_folder(self):
        folder = filedialog.askdirectory(initialdir=self.source_dir.get())
        if folder:
            self.source_dir.set(folder)

    def log(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def start_organize(self):
        if self.is_running:
            return

        source = self.source_dir.get().strip()
        if not source or not os.path.isdir(source):
            self.log(f"Error: '{source}' is not a valid folder.")
            return

        self.is_running = True
        self.run_button.configure(state="disabled", text="Organizing...")
        self.progress_bar.set(0)
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

        thread = threading.Thread(target=self.organize, args=(source,), daemon=True)
        thread.start()

    def organize(self, source_dir):
        try:
            entries = [f for f in os.listdir(source_dir)
                       if os.path.isfile(os.path.join(source_dir, f))]
            total = len(entries)

            if total == 0:
                self.after(0, self.log, "No files found to organize.")
            else:
                for i, file in enumerate(entries, start=1):
                    file_path = os.path.join(source_dir, file)
                    ext = os.path.splitext(file)[1].lower()
                    moved = False

                    for folder, extensions in FILE_TYPES.items():
                        if ext in extensions:
                            dest = os.path.join(source_dir, folder)
                            os.makedirs(dest, exist_ok=True)
                            shutil.move(file_path, os.path.join(dest, file))
                            self.after(0, self.log, f"Moved '{file}' -> {folder}/")
                            moved = True
                            break

                    if not moved:
                        dest = os.path.join(source_dir, "Other")
                        os.makedirs(dest, exist_ok=True)
                        shutil.move(file_path, os.path.join(dest, file))
                        self.after(0, self.log, f"Moved '{file}' -> Other/")

                    self.after(0, self.progress_bar.set, i / total)

                self.after(0, self.log, f"Done. Organized {total} file(s).")

        except Exception as e:
            self.after(0, self.log, f"Error: {e}")
        finally:
            self.after(0, self.progress_bar.set, 1)
            self.after(0, self._reset_button)

    def _reset_button(self):
        self.is_running = False
        self.run_button.configure(state="normal", text="Organize Files")


if __name__ == "__main__":
    app = OrganizerApp()
    app.mainloop()
