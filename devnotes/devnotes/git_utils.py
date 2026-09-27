"""Lightweight git context detection.

This is a QOL feature: when you jot a note down inside a git repo,
devnotes automatically tags it with the repo name and current branch,
so later you can filter notes by project without typing anything.
No subprocess to `git` binary required beyond a simple call, and it
fails silently (returns None) if git isn't available or you're not
in a repo — never blocks note-taking.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple


def _run(args: list[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def get_repo_name() -> Optional[str]:
    top = _run(["rev-parse", "--show-toplevel"])
    if not top:
        return None
    return Path(top).name


def get_branch() -> Optional[str]:
    return _run(["rev-parse", "--abbrev-ref", "HEAD"])


def get_context() -> Tuple[Optional[str], Optional[str]]:
    """Returns (repo_name, branch) or (None, None) if not in a git repo."""
    repo = get_repo_name()
    if repo is None:
        return None, None
    return repo, get_branch()
