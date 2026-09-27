#!/usr/bin/env python3
"""Single entry point for devnotes — no `pip install -e .` required.

    python main.py              -> launches the desktop GUI
    python main.py list         -> runs any CLI command (add, list, show, ...)
    python main.py --help       -> full CLI help

Just needs the dependencies from requirements.txt (`pip install -r
requirements.txt`, or `pip install -r requirements.txt --break-system-packages`
on newer Debian/Ubuntu). Works from this folder as-is because it adds
itself to sys.path before importing the devnotes package sitting next
to it.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the local `devnotes/` package importable without installation.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    if len(sys.argv) > 1:
        # Any arguments -> treat this like the `devnotes` CLI.
        # e.g. `python main.py add "fix bug" -t bug` or `python main.py list`
        from devnotes.cli import cli

        cli(prog_name="devnotes", args=sys.argv[1:])
    else:
        # No arguments -> launch the GUI.
        try:
            from devnotes.gui import main as gui_main
        except ImportError as exc:
            print(
                "Couldn't start the GUI (missing dependency: "
                f"{exc.name}). Run: pip install -r requirements.txt\n"
                "Or use the CLI instead, e.g. `python main.py --help`.",
                file=sys.stderr,
            )
            sys.exit(1)
        gui_main()


if __name__ == "__main__":
    main()
