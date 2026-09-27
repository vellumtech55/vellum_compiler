"""Date/grid math for the 45-day forward-planning calendar.

The calendar is a pipeline into devnotes: every day in the window
maps 1:1 to a note tagged `daily:YYYY-MM-DD`. Opening a day either
opens its existing note or creates a fresh one — that's the whole
"pipeline". This module only handles the date arithmetic; see
`db.py` (get_or_create_daily_note / daily_note_dates) for the DB
side and `cli.py` / `gui.py` for the two front ends.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

DAILY_TAG_PREFIX = "daily:"
DEFAULT_WINDOW_DAYS = 45
WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def daily_tag(d: date) -> str:
    return f"{DAILY_TAG_PREFIX}{d.isoformat()}"


def parse_date(s: str) -> date:
    """Accepts an ISO date ('2026-09-04') or the words 'today'/'tomorrow'."""
    s = s.strip().lower()
    if s == "today":
        return date.today()
    if s == "tomorrow":
        return date.today() + timedelta(days=1)
    return date.fromisoformat(s)


def forward_window(days: int = DEFAULT_WINDOW_DAYS, start: Optional[date] = None) -> list[date]:
    """The next `days` days starting from `start` (default: today), inclusive."""
    start = start or date.today()
    return [start + timedelta(days=i) for i in range(days)]


@dataclass
class DayCell:
    day: date
    in_window: bool  # False for padding cells outside the requested range


def weeks_grid(days: list[date]) -> list[list[Optional[DayCell]]]:
    """Arrange consecutive dates into Mon-Sun week rows, padding both
    ends with None so every row has exactly 7 cells."""
    if not days:
        return []
    grid: list[list[Optional[DayCell]]] = []
    row: list[Optional[DayCell]] = [None] * days[0].weekday()  # Mon=0
    for d in days:
        row.append(DayCell(day=d, in_window=True))
        if len(row) == 7:
            grid.append(row)
            row = []
    if row:
        row.extend([None] * (7 - len(row)))
        grid.append(row)
    return grid


def month_headers(grid: list[list[Optional[DayCell]]]) -> list[Optional[str]]:
    """One label per week row: the month name whenever the row starts
    a new month (or is the first row), else None."""
    labels: list[Optional[str]] = []
    last_month = None
    for row in grid:
        first_real = next((c.day for c in row if c is not None), None)
        if first_real and first_real.month != last_month:
            labels.append(first_real.strftime("%b %Y"))
            last_month = first_real.month
        else:
            labels.append(None)
    return labels
