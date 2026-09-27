"""Open $EDITOR for composing/editing note bodies — because typing a
multi-line note as a shell argument is miserable."""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile


def _default_editor() -> str:
    if os.name == "nt":
        return "notepad"
    return "vi"


def edit_text(initial_text: str = "", suffix: str = ".md") -> str:
    editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL") or _default_editor()
    # Support editors invoked with flags, e.g. EDITOR="code --wait"
    try:
        parts = shlex.split(editor_cmd)
    except ValueError:
        parts = [editor_cmd]

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as tf:
        tf.write(initial_text)
        path = tf.name
    try:
        subprocess.call([*parts, path])
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Editor '{editor_cmd}' not found. Set $EDITOR to your preferred editor.", file=sys.stderr)
        return initial_text
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
