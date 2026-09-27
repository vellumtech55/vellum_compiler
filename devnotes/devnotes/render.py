"""All terminal presentation lives here.

Key QOL feature: fenced code blocks (```python ... ```) inside a note
body are detected and rendered with real syntax highlighting instead
of as flat text, so a "dev notes" app actually feels good for pasting
snippets into.
"""
from __future__ import annotations

import re
from typing import Iterable

from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from .db import Note

console = Console()

_CODE_FENCE = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)


def render_body(body: str):
    """Split a note body into text/code segments and return a rich
    renderable Group that syntax-highlights fenced code blocks while
    rendering surrounding prose as Markdown (bullets, bold, etc.)."""
    parts = []
    last_end = 0
    for match in _CODE_FENCE.finditer(body):
        pre = body[last_end : match.start()]
        if pre.strip():
            parts.append(Markdown(pre.strip()))
        lang = match.group(1) or "text"
        code = match.group(2).rstrip("\n")
        parts.append(
            Syntax(code, lang, theme="monokai", line_numbers=True, word_wrap=True)
        )
        last_end = match.end()
    tail = body[last_end:]
    if tail.strip():
        parts.append(Markdown(tail.strip()))
    if not parts:
        parts.append(Text(body, style="dim italic") if not body else Text(body))
    return Group(*parts)


def _tag_text(tags: list[str]) -> Text:
    t = Text()
    for i, tag in enumerate(tags):
        if i:
            t.append(" ")
        t.append(f" #{tag} ", style="black on cyan")
    return t


def note_title_line(note: Note) -> str:
    pin = "📌 " if note.pinned else ""
    arc = " [archived]" if note.archived else ""
    proj = f" [dim]({note.project})[/dim]" if note.project else ""
    return f"{pin}#{note.id} · {note.title}{proj}{arc}"


def print_note(note: Note, full: bool = True) -> None:
    body_renderable = render_body(note.body) if full else Text(
        (note.body.strip().splitlines() or [""])[0][:100], style="dim"
    )
    footer = Text(f"created {note.created_at}  ·  updated {note.updated_at}", style="dim")
    group_items = [body_renderable]
    if note.tags:
        group_items.append(_tag_text(note.tags))
    group_items.append(footer)
    console.print(
        Panel(
            Group(*group_items),
            title=note_title_line(note),
            title_align="left",
            border_style="cyan" if note.pinned else "grey50",
        )
    )


def print_notes_table(notes: Iterable[Note]) -> None:
    notes = list(notes)
    if not notes:
        console.print("[dim]No notes found.[/dim]")
        return
    table = Table(show_lines=False, expand=True)
    table.add_column("ID", style="bold", width=5, justify="right")
    table.add_column("", width=2)
    table.add_column("Title", ratio=3, overflow="fold")
    table.add_column("Project", style="magenta", ratio=1)
    table.add_column("Tags", ratio=2, overflow="fold")
    table.add_column("Updated", style="dim", ratio=1)

    for n in notes:
        pin = "📌" if n.pinned else ""
        tags = " ".join(f"#{t}" for t in n.tags)
        table.add_row(
            str(n.id),
            pin,
            n.title,
            n.project or "",
            tags,
            n.updated_at.replace("T", " "),
        )
    console.print(table)


def print_stats(stats: dict, tags: list[tuple[str, int]], projects: list[tuple[str, int]]) -> None:
    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="bold cyan")
    summary.add_column()
    for label, key in [
        ("Active", "active"),
        ("Archived", "archived"),
        ("Pinned", "pinned"),
        ("Tags", "tags"),
        ("Projects", "projects"),
    ]:
        summary.add_row(str(stats[key]), label)
    console.print(Panel(summary, title="devnotes stats", border_style="cyan"))

    if tags:
        t = Table(title="Top tags")
        t.add_column("Tag")
        t.add_column("Count", justify="right")
        for name, cnt in tags[:10]:
            t.add_row(f"#{name}", str(cnt))
        console.print(t)

    if projects:
        p = Table(title="Projects")
        p.add_column("Project")
        p.add_column("Notes", justify="right")
        for name, cnt in projects[:10]:
            p.add_row(name, str(cnt))
        console.print(p)


def success(msg: str) -> None:
    console.print(f"[bold green]✓[/bold green] {msg}")


def warn(msg: str) -> None:
    console.print(f"[bold yellow]![/bold yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[bold red]✗[/bold red] {msg}")


def print_calendar(grid, month_labels, note_counts: dict, today) -> None:
    """Render a 45-day-forward planner grid: one column per weekday,
    one row per week, day cells marked when a daily note exists.
    `grid`/`month_labels` come from calendar_utils.weeks_grid/month_headers.
    `note_counts` maps ISO date string -> note count.
    """
    from .calendar_utils import WEEKDAY_LABELS

    table = Table(show_header=True, header_style="bold", show_lines=False, box=None, padding=(0, 1))
    table.add_column("Month", style="dim", width=8)
    for label in WEEKDAY_LABELS:
        table.add_column(label, justify="center", width=4)

    for row, month_label in zip(grid, month_labels):
        cells = [month_label or ""]
        for cell in row:
            if cell is None:
                cells.append("")
                continue
            d = cell.day
            iso = d.isoformat()
            count = note_counts.get(iso, 0)
            day_str = f"{d.day:>2}"
            if d == today:
                text = f"[bold black on cyan]{day_str}[/bold black on cyan]"
            elif count > 0:
                text = f"[bold green]{day_str}●[/bold green]"
            else:
                text = f"[dim]{day_str}[/dim]"
            cells.append(text)
        table.add_row(*cells)

    console.print(table)
    console.print(
        "[dim]● = note exists   [/dim][bold black on cyan] today [/bold black on cyan]"
    )
