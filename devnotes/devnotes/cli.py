"""devnotes — a dev-focused notes CLI.

Run `devnotes --help` or any subcommand's `--help` for details.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import click

from . import calendar_utils as cal
from . import db, git_utils, render
from .editor import edit_text
from .paths import backup_dir
from .templates import get_template, template_names


def _split_tags(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [t.strip().lstrip("#") for t in tags.split(",") if t.strip()]


@click.group(invoke_without_command=True)
@click.pass_context
@click.version_option(package_name="devnotes")
def cli(ctx: click.Context) -> None:
    """devnotes: quick, taggable, git-aware notes for developers."""
    db.init_db()
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# --------------------------------------------------------------------------- #
# add / quick capture
# --------------------------------------------------------------------------- #
@cli.command()
@click.argument("title", nargs=-1)
@click.option("-b", "--body", default=None, help="Note body text (skips $EDITOR).")
@click.option("-t", "--tags", default=None, help="Comma-separated tags, e.g. -t bug,api")
@click.option(
    "-T",
    "--template",
    "template_name",
    type=click.Choice(template_names()),
    default=None,
    help="Start body from a template.",
)
@click.option("-p", "--project", default=None, help="Override auto-detected git project name.")
@click.option("--pin/--no-pin", default=False, help="Pin the note immediately.")
@click.option("--no-git", is_flag=True, help="Skip git repo/branch auto-tagging.")
def add(title, body, tags, template_name, project, pin, no_git):
    """Add a note. Opens $EDITOR for the body unless --body is given.

    Examples:

      devnotes add "Fix flaky auth test" -t bug,ci

      devnotes add "Sprint retro notes" -T meeting
    """
    title_str = " ".join(title).strip()
    if not title_str:
        title_str = click.prompt("Title")

    repo, branch = (None, None) if no_git else git_utils.get_context()
    if project is None:
        project = repo

    if body is None:
        seed = get_template(template_name) if template_name else ""
        body = edit_text(seed)

    tag_list = _split_tags(tags)
    if branch and branch not in tag_list:
        tag_list.append(f"branch:{branch}")

    note_id = db.add_note(
        title=title_str,
        body=body,
        tags=tag_list,
        project=project,
        branch=branch,
        pinned=pin,
    )
    render.success(f"Saved note #{note_id}" + (f" (project: {project})" if project else ""))


@cli.command()
@click.argument("text", nargs=-1, required=True)
def quick(text):
    """Fastest possible capture: one line, no editor, no prompts.

    devnotes quick "remember to rotate the API key" #ops #security
    """
    raw = " ".join(text)
    words = raw.split()
    tags = [w.lstrip("#") for w in words if w.startswith("#")]
    title = " ".join(w for w in words if not w.startswith("#")).strip() or "(quick note)"
    repo, branch = git_utils.get_context()
    if branch:
        tags.append(f"branch:{branch}")
    note_id = db.add_note(title=title, body="", tags=tags, project=repo, branch=branch)
    render.success(f"Quick note #{note_id} saved.")


# --------------------------------------------------------------------------- #
# list / show / search
# --------------------------------------------------------------------------- #
@cli.command("list")
@click.option("-p", "--project", default=None)
@click.option("-t", "--tag", default=None)
@click.option("-a", "--all", "show_all", is_flag=True, help="Include archived notes.")
@click.option("--pinned", is_flag=True, help="Only pinned notes.")
@click.option("-n", "--limit", type=int, default=None)
@click.option("--since", default=None, help="Only notes updated since, e.g. '3d', '1w', '2026-08-01'.")
def list_cmd(project, tag, show_all, pinned, limit, since):
    """List notes as a table. Filters combine (AND)."""
    notes = db.list_notes(
        project=project, tag=tag, include_archived=show_all, pinned_only=pinned, limit=limit
    )
    if since:
        cutoff = _parse_since(since)
        if cutoff:
            notes = [n for n in notes if n.updated_at >= cutoff.isoformat(timespec="seconds")]
    render.print_notes_table(notes)


def _parse_since(spec: str) -> datetime | None:
    spec = spec.strip().lower()
    try:
        if spec.endswith("d"):
            return datetime.now() - timedelta(days=int(spec[:-1]))
        if spec.endswith("w"):
            return datetime.now() - timedelta(weeks=int(spec[:-1]))
        if spec.endswith("h"):
            return datetime.now() - timedelta(hours=int(spec[:-1]))
        return datetime.fromisoformat(spec)
    except ValueError:
        render.warn(f"Couldn't parse --since '{spec}', ignoring filter.")
        return None


@cli.command()
@click.argument("note_id", type=int)
def show(note_id):
    """Show a single note in full, with syntax-highlighted code blocks."""
    note = db.get_note(note_id)
    if not note:
        render.error(f"No note #{note_id}")
        sys.exit(1)
    render.print_note(note, full=True)


@cli.command()
@click.argument("query", nargs=-1, required=True)
@click.option("-p", "--project", default=None)
def search(query, project):
    """Full-text search across titles and bodies."""
    q = " ".join(query)
    notes = db.list_notes(query=q, project=project, include_archived=True)
    render.console.print(f"[dim]{len(notes)} match(es) for[/dim] '{q}'")
    render.print_notes_table(notes)


# --------------------------------------------------------------------------- #
# edit / mutate
# --------------------------------------------------------------------------- #
@cli.command()
@click.argument("note_id", type=int)
@click.option("-t", "--title", default=None, help="New title.")
@click.option("--tags", default=None, help="Replace tags (comma-separated).")
def edit(note_id, title, tags):
    """Edit a note's body in $EDITOR (and optionally title/tags)."""
    note = db.get_note(note_id)
    if not note:
        render.error(f"No note #{note_id}")
        sys.exit(1)
    new_body = edit_text(note.body)
    tag_list = _split_tags(tags) if tags is not None else None
    db.update_note(note_id, title=title, body=new_body, tags=tag_list)
    render.success(f"Updated note #{note_id}")


@cli.command()
@click.argument("note_id", type=int)
def pin(note_id):
    """Pin a note so it always sorts to the top of `list`."""
    if db.set_flag(note_id, "pinned", True):
        render.success(f"Pinned #{note_id}")
    else:
        render.error(f"No note #{note_id}")


@cli.command()
@click.argument("note_id", type=int)
def unpin(note_id):
    """Unpin a note."""
    if db.set_flag(note_id, "pinned", False):
        render.success(f"Unpinned #{note_id}")
    else:
        render.error(f"No note #{note_id}")


@cli.command()
@click.argument("note_id", type=int)
def archive(note_id):
    """Archive a note (hidden from default `list`, kept in DB)."""
    if db.set_flag(note_id, "archived", True):
        render.success(f"Archived #{note_id}")
    else:
        render.error(f"No note #{note_id}")


@cli.command()
@click.argument("note_id", type=int)
def unarchive(note_id):
    """Restore an archived note."""
    if db.set_flag(note_id, "archived", False):
        render.success(f"Restored #{note_id}")
    else:
        render.error(f"No note #{note_id}")


@cli.command()
@click.argument("note_id", type=int)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def rm(note_id, yes):
    """Permanently delete a note. Use `archive` instead if unsure."""
    note = db.get_note(note_id)
    if not note:
        render.error(f"No note #{note_id}")
        sys.exit(1)
    if not yes and not click.confirm(f"Permanently delete #{note_id} '{note.title}'?"):
        render.warn("Cancelled.")
        return
    db.delete_note(note_id)
    render.success(f"Deleted #{note_id}")


# --------------------------------------------------------------------------- #
# overview commands
# --------------------------------------------------------------------------- #
@cli.command()
def tags():
    """List all tags with note counts."""
    for name, count in db.all_tags_with_counts():
        render.console.print(f"  [cyan]#{name}[/cyan]  [dim]{count}[/dim]")


@cli.command()
def projects():
    """List all auto-detected/assigned projects with note counts."""
    for name, count in db.all_projects_with_counts():
        render.console.print(f"  [magenta]{name}[/magenta]  [dim]{count}[/dim]")


@cli.command()
def stats():
    """Show a dashboard of note/tag/project counts."""
    render.print_stats(db.stats(), db.all_tags_with_counts(), db.all_projects_with_counts())


# --------------------------------------------------------------------------- #
# calendar pipeline: 45-day forward planner -> one note per day
# --------------------------------------------------------------------------- #
@cli.command()
@click.option("-n", "--days", type=int, default=cal.DEFAULT_WINDOW_DAYS, show_default=True)
@click.option(
    "-s", "--start", default=None, help="First day of the window (ISO date, default: today)."
)
def calendar(days, start):
    """Show the forward-planning calendar. Green dot = a note exists
    for that day; click nothing here, just look — use `today`/`day`
    to open or create one."""
    start_date = cal.parse_date(start) if start else None
    window = cal.forward_window(days=days, start=start_date)
    grid = cal.weeks_grid(window)
    labels = cal.month_headers(grid)
    counts = db.daily_note_dates()
    render.print_calendar(grid, labels, counts, today=datetime.now().date())


def _open_daily_note(target_date, tags, project):
    """Shared logic for `today`/`day`: open-or-create the note for a
    date, edit it in $EDITOR, save. This is the calendar->devnotes
    pipeline's single entry point."""
    iso = target_date.isoformat()
    weekday = target_date.strftime("%A")
    title = f"Plan: {iso} ({weekday})"
    note, created = db.get_or_create_daily_note(
        iso, title=title, project=project, extra_tags=tags
    )
    new_body = edit_text(note.body)
    db.update_note(note.id, body=new_body)
    verb = "Created" if created else "Updated"
    render.success(f"{verb} plan for {iso} (note #{note.id})")


@cli.command()
@click.option("-t", "--tags", default=None, help="Extra tags for a brand-new day note.")
@click.option("-p", "--project", default=None)
def today(tags, project):
    """Open (or create) today's note in the calendar pipeline."""
    _open_daily_note(datetime.now().date(), _split_tags(tags), project)


@cli.command()
@click.argument("date_str", metavar="DATE")
@click.option("-t", "--tags", default=None, help="Extra tags for a brand-new day note.")
@click.option("-p", "--project", default=None)
def day(date_str, tags, project):
    """Open (or create) the note for a specific day.

    DATE accepts an ISO date (2026-09-20), 'today', or 'tomorrow'.
    """
    try:
        target = cal.parse_date(date_str)
    except ValueError:
        render.error(f"Couldn't parse date '{date_str}'. Use YYYY-MM-DD, 'today', or 'tomorrow'.")
        sys.exit(1)
    _open_daily_note(target, _split_tags(tags), project)


# --------------------------------------------------------------------------- #
# import / export
# --------------------------------------------------------------------------- #
@cli.command()
@click.option("-o", "--output", type=click.Path(), default=None, help="Output file path.")
def export(output):
    """Export every note (including archived) to a JSON backup file."""
    notes = db.list_notes(include_archived=True)
    payload = [
        {
            "id": n.id,
            "title": n.title,
            "body": n.body,
            "project": n.project,
            "branch": n.branch,
            "pinned": n.pinned,
            "archived": n.archived,
            "tags": n.tags,
            "created_at": n.created_at,
            "updated_at": n.updated_at,
        }
        for n in notes
    ]
    if output is None:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = str(backup_dir() / f"devnotes-{ts}.json")
    Path(output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    render.success(f"Exported {len(payload)} notes to {output}")


@cli.command("import")
@click.argument("path", type=click.Path(exists=True))
def import_cmd(path):
    """Import notes from a JSON backup produced by `export`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    count = 0
    for item in data:
        db.add_note(
            title=item.get("title", "(untitled)"),
            body=item.get("body", ""),
            tags=item.get("tags", []),
            project=item.get("project"),
            branch=item.get("branch"),
            pinned=item.get("pinned", False),
        )
        count += 1
    render.success(f"Imported {count} notes from {path}")


@cli.command()
@click.argument("note_id", type=int)
@click.option("-o", "--output", type=click.Path(), default=None)
def export_md(note_id, output):
    """Export a single note to a standalone Markdown file."""
    note = db.get_note(note_id)
    if not note:
        render.error(f"No note #{note_id}")
        sys.exit(1)
    lines = [f"# {note.title}", ""]
    if note.tags:
        lines.append(" ".join(f"#{t}" for t in note.tags))
        lines.append("")
    lines.append(note.body)
    content = "\n".join(lines)
    output = output or f"note-{note_id}.md"
    Path(output).write_text(content, encoding="utf-8")
    render.success(f"Exported note #{note_id} to {output}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
