"""SQLite persistence layer for devnotes.

Schema is intentionally simple (3 tables) but supports every QOL
feature in the CLI: tags, pinning, archiving, project scoping and
plain-text search (LIKE-based — FTS5 isn't guaranteed to be compiled
into every Python's sqlite3, so we don't depend on it).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, Optional

from .paths import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    project     TEXT,
    branch      TEXT,
    pinned      INTEGER NOT NULL DEFAULT 0,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_notes_project ON notes(project);
CREATE INDEX IF NOT EXISTS idx_notes_pinned ON notes(pinned);
CREATE INDEX IF NOT EXISTS idx_notes_archived ON notes(archived);
"""


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@dataclass
class Note:
    id: int
    title: str
    body: str
    project: Optional[str]
    branch: Optional[str]
    pinned: bool
    archived: bool
    created_at: str
    updated_at: str
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_row(cls, row: sqlite3.Row, tags: list[str]) -> "Note":
        return cls(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            project=row["project"],
            branch=row["branch"],
            pinned=bool(row["pinned"]),
            archived=bool(row["archived"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            tags=tags,
        )


def _tags_for(conn: sqlite3.Connection, note_id: int) -> list[str]:
    rows = conn.execute(
        """SELECT t.name FROM tags t
           JOIN note_tags nt ON nt.tag_id = t.id
           WHERE nt.note_id = ? ORDER BY t.name""",
        (note_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def _get_or_create_tag(conn: sqlite3.Connection, name: str) -> int:
    name = name.strip().lstrip("#")
    if not name:
        return -1
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute("INSERT INTO tags(name) VALUES (?)", (name,))
    return cur.lastrowid


def add_note(
    title: str,
    body: str = "",
    tags: Optional[list[str]] = None,
    project: Optional[str] = None,
    branch: Optional[str] = None,
    pinned: bool = False,
) -> int:
    ts = now()
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO notes(title, body, project, branch, pinned, archived, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 0, ?, ?)""",
            (title, body, project, branch, int(pinned), ts, ts),
        )
        note_id = cur.lastrowid
        for tag in tags or []:
            tag_id = _get_or_create_tag(conn, tag)
            if tag_id != -1:
                conn.execute(
                    "INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?, ?)",
                    (note_id, tag_id),
                )
        return note_id


def update_note(
    note_id: int,
    title: Optional[str] = None,
    body: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> bool:
    with connect() as conn:
        row = conn.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return False
        fields, values = [], []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if body is not None:
            fields.append("body = ?")
            values.append(body)
        fields.append("updated_at = ?")
        values.append(now())
        values.append(note_id)
        conn.execute(f"UPDATE notes SET {', '.join(fields)} WHERE id = ?", values)
        if tags is not None:
            conn.execute("DELETE FROM note_tags WHERE note_id = ?", (note_id,))
            for tag in tags:
                tag_id = _get_or_create_tag(conn, tag)
                if tag_id != -1:
                    conn.execute(
                        "INSERT OR IGNORE INTO note_tags(note_id, tag_id) VALUES (?, ?)",
                        (note_id, tag_id),
                    )
        return True


def set_flag(note_id: int, field_name: str, value: bool) -> bool:
    assert field_name in ("pinned", "archived")
    with connect() as conn:
        cur = conn.execute(
            f"UPDATE notes SET {field_name} = ?, updated_at = ? WHERE id = ?",
            (int(value), now(), note_id),
        )
        return cur.rowcount > 0


def delete_note(note_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        return cur.rowcount > 0


def get_note(note_id: int) -> Optional[Note]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if not row:
            return None
        return Note.from_row(row, _tags_for(conn, note_id))


def list_notes(
    project: Optional[str] = None,
    tag: Optional[str] = None,
    query: Optional[str] = None,
    include_archived: bool = False,
    pinned_only: bool = False,
    limit: Optional[int] = None,
) -> list[Note]:
    sql = "SELECT DISTINCT notes.* FROM notes"
    joins = []
    where = []
    params: list = []

    if tag:
        joins.append(
            "JOIN note_tags nt ON nt.note_id = notes.id "
            "JOIN tags t ON t.id = nt.tag_id"
        )
        where.append("t.name = ? COLLATE NOCASE")
        params.append(tag)
    if project:
        where.append("notes.project = ?")
        params.append(project)
    if query:
        where.append("(notes.title LIKE ? OR notes.body LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    if not include_archived:
        where.append("notes.archived = 0")
    if pinned_only:
        where.append("notes.pinned = 1")

    sql += " " + " ".join(joins)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY notes.pinned DESC, notes.updated_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"

    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [Note.from_row(r, _tags_for(conn, r["id"])) for r in rows]


def all_tags_with_counts() -> list[tuple[str, int]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.name, COUNT(nt.note_id) as cnt FROM tags t
               LEFT JOIN note_tags nt ON nt.tag_id = t.id
               GROUP BY t.id ORDER BY cnt DESC, t.name"""
        ).fetchall()
        return [(r["name"], r["cnt"]) for r in rows]


def all_projects_with_counts() -> list[tuple[str, int]]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT project, COUNT(*) as cnt FROM notes
               WHERE project IS NOT NULL AND archived = 0
               GROUP BY project ORDER BY cnt DESC"""
        ).fetchall()
        return [(r["project"], r["cnt"]) for r in rows]


def daily_note_dates(prefix: str = "daily:") -> dict[str, int]:
    """Map of ISO date string -> note count, for every note tagged
    with the given daily-tag prefix. Powers the calendar's "which
    days already have a note" highlighting."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT t.name, COUNT(DISTINCT nt.note_id) AS cnt
               FROM tags t
               JOIN note_tags nt ON nt.tag_id = t.id
               JOIN notes n ON n.id = nt.note_id
               WHERE t.name LIKE ? AND n.archived = 0
               GROUP BY t.name""",
            (f"{prefix}%",),
        ).fetchall()
        return {r["name"][len(prefix):]: r["cnt"] for r in rows}


def get_daily_note(date_str: str, prefix: str = "daily:") -> Optional[Note]:
    """Return the note tagged `{prefix}{date_str}`, if one exists."""
    notes = list_notes(tag=f"{prefix}{date_str}", include_archived=True)
    return notes[0] if notes else None


def get_or_create_daily_note(
    date_str: str,
    title: str,
    prefix: str = "daily:",
    project: Optional[str] = None,
    extra_tags: Optional[list[str]] = None,
) -> tuple[Note, bool]:
    """Return (note, created). This is the calendar->devnotes pipeline:
    each calendar day maps 1:1 to a note tagged `{prefix}{date_str}`,
    created on first use and simply reopened after that."""
    existing = get_daily_note(date_str, prefix=prefix)
    if existing:
        return existing, False
    tags = [f"{prefix}{date_str}"] + (extra_tags or [])
    note_id = add_note(title=title, body="", tags=tags, project=project)
    return get_note(note_id), True


def stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM notes").fetchone()["c"]
        archived = conn.execute("SELECT COUNT(*) c FROM notes WHERE archived=1").fetchone()["c"]
        pinned = conn.execute("SELECT COUNT(*) c FROM notes WHERE pinned=1").fetchone()["c"]
        tags = conn.execute("SELECT COUNT(*) c FROM tags").fetchone()["c"]
        projects = conn.execute(
            "SELECT COUNT(DISTINCT project) c FROM notes WHERE project IS NOT NULL"
        ).fetchone()["c"]
        return {
            "total": total,
            "active": total - archived,
            "archived": archived,
            "pinned": pinned,
            "tags": tags,
            "projects": projects,
        }
