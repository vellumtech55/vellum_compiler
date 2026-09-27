"""Central place for filesystem locations used by devnotes."""
from __future__ import annotations

import os
from pathlib import Path

APP_DIR_ENV = "DEVNOTES_HOME"


def app_dir() -> Path:
    """Return (and create) the directory devnotes stores its data in.

    Respects $DEVNOTES_HOME if set, otherwise uses ~/.devnotes.
    This makes it trivial to point a project-local instance at a
    different folder (e.g. `DEVNOTES_HOME=.devnotes devnotes list`).
    """
    override = os.environ.get(APP_DIR_ENV)
    base = Path(override).expanduser() if override else Path.home() / ".devnotes"
    base.mkdir(parents=True, exist_ok=True)
    return base


def db_path() -> Path:
    return app_dir() / "notes.db"


def config_path() -> Path:
    return app_dir() / "config.json"


def backup_dir() -> Path:
    d = app_dir() / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d
