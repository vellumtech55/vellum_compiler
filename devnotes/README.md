# devnotes

A fast, no-nonsense notes app built for developers — because sticky
notes and a random `notes.txt` don't scale. Everything is local
SQLite, everything works offline, and it's built around the way devs
actually work: git branches, code snippets, tags, and quick capture.

Ships as **both** a CLI (`devnotes`) and a desktop GUI (`devnotes-gui`)
— they share the exact same SQLite database, so a note you jot down
in one shows up instantly in the other.

## Quality-of-life features

- **Git-aware auto-tagging** — run `devnotes add` inside a repo and the
  note is automatically stamped with the repo name (as `project`) and
  the current branch (as a `branch:*` tag). No setup required.
- **Syntax-highlighted code blocks** — write fenced code blocks
  (```` ```python ... ``` ````) in a note body and `devnotes show`
  renders them with real syntax highlighting and line numbers via
  `rich`. Everything else renders as Markdown.
- **$EDITOR integration** — `add` and `edit` drop you into your real
  editor (vim, nano, VS Code, whatever `$EDITOR` points to — flags
  like `EDITOR="code --wait"` work too) instead of a cramped one-line
  prompt.
- **Templates** — `-T bug`, `-T meeting`, `-T todo`, `-T idea`,
  `-T decision`, `-T snippet` pre-fill a sensible structure so you're
  not retyping the same headings every time.
- **Tags & projects** — free-form tags plus automatic project
  scoping; filter, list counts, and cross-reference either.
- **Full-text search** — `devnotes search <query>` across every
  title and body.
- **Pin / archive** — pin your active fires to the top of `list`;
  archive stale notes instead of deleting them.
- **`quick` capture** — one line, no editor, no prompts:
  `devnotes quick "rotate api keys #ops #security"`.
- **`--since` filters** — `devnotes list --since 3d` / `1w` / an ISO
  date.
- **JSON export/import** — full backups, plus one-off
  `export-md <id>` to hand a single note to someone as Markdown.
- **Portable data dir** — defaults to `~/.devnotes`, override with
  `DEVNOTES_HOME` for a project-local notes DB.

## Calendar pipeline (45-day planner)

A forward-looking 45-day calendar that pipelines directly into
devnotes: **every day is a note.** Open a day and devnotes either
creates a fresh note tagged `daily:YYYY-MM-DD` or reopens the one
already there — same note, same tag, whether you get to it from the
CLI or the GUI.

CLI:

```bash
devnotes calendar              # print the 45-day grid (green dot = has a note)
devnotes calendar -n 30        # shorter window
devnotes calendar -s 2026-10-01  # start the window on a specific date
devnotes today                 # open (or create) today's plan in $EDITOR
devnotes day 2026-09-20        # open (or create) a specific day's plan
devnotes day tomorrow          # 'today' and 'tomorrow' both work as shorthand
```

GUI: click **Cal** next to "+ New Note" (or `Ctrl+Shift+C`) to open
the 45-day grid — click any day to open or create its note. `Ctrl+T`
jumps straight to today's plan. Days that already have a note are
highlighted green; today is highlighted blue.

Because it's just a tag, every day-note is also fully queryable
through the regular note tools: `devnotes list -t daily:2026-09-20`,
`devnotes search`, pin/archive, etc. all work on them normally.

## GUI

Run `devnotes-gui` for a dark-themed desktop app: a sidebar with
search/tag/project filters and a note list, an editor pane with
title/tags/project fields, and a body editor with **live syntax
highlighting** of fenced code blocks (via Pygments) plus lightweight
Markdown highlighting (headers, `` `inline code` ``, **bold**,
`- [ ]` checkboxes, `#tags`).

Other GUI QOL touches: auto-detects the current git repo/branch on
launch and pre-fills them on new notes, undo/redo in the editor,
unsaved-changes prompts before you lose work, one-click pin/archive/
delete, an Insert Template menu, the 45-day calendar planner, and the
same JSON export/import and Markdown export as the CLI.

Keyboard shortcuts: `Ctrl+N` new note · `Ctrl+S` / `Ctrl+Enter` save ·
`Ctrl+F` focus search · `Ctrl+P` toggle pin · `Ctrl+Shift+A` toggle
archive · `Ctrl+Backspace` delete · `Ctrl+Shift+C` open calendar ·
`Ctrl+T` today's plan · `Ctrl+Q` quit.

## Quick start (no install)

```bash
pip install -r requirements.txt
python main.py             # launches the GUI
python main.py list        # or any CLI command, e.g. add / show / search
```

`main.py` sits at the project root and works straight out of the zip
— no `pip install -e .` needed. Run it with no arguments to open the
desktop GUI, or with any CLI command/arguments to use it exactly like
the `devnotes` command below.

## Install as a command (optional)

```bash
pip install -e ".[gui]"
```

This additionally installs the `devnotes` (CLI) and `devnotes-gui`
commands onto your PATH, so you can run `devnotes` / `devnotes-gui`
from anywhere instead of `python main.py`.

Requires Python 3.9+. Core dependencies are `click` and `rich`;
`.[gui]` additionally pulls in `Pygments` for code syntax
highlighting in the GUI (the GUI still runs without it — code blocks
just won't be colored token-by-token).

The GUI uses `tkinter`, which ships with most Python installs on
Windows and macOS. On Linux you may need to install it separately,
e.g. `sudo apt install python3-tk` (Debian/Ubuntu) or the equivalent
for your distro.

## Quick start

```bash
# Inside any git repo:
devnotes add "Fix flaky auth test" -t bug,auth --pin
# -> opens $EDITOR for the body, auto-tags with repo + branch

devnotes quick "remember to rotate the API key #ops"

devnotes add "Sprint retro" -T meeting

devnotes list                 # table of active notes, pinned first
devnotes list -t bug          # filter by tag
devnotes list -p my-repo      # filter by project
devnotes list --since 3d      # updated in the last 3 days

devnotes show 1               # full note, code blocks highlighted
devnotes search "flaky"       # full-text search
devnotes edit 1               # reopen in $EDITOR
devnotes pin 1 / unpin 1
devnotes archive 1 / unarchive 1
devnotes rm 1                 # permanent delete (asks to confirm)

devnotes tags                 # tag cloud with counts
devnotes projects             # project list with counts
devnotes stats                # dashboard

devnotes export               # JSON backup to ~/.devnotes/backups/
devnotes import backup.json   # restore from a backup
devnotes export-md 1          # single note -> Markdown file
```

Run `devnotes --help` or `devnotes <command> --help` any time — every
command is documented there too.

## Data location

Everything lives in a single SQLite file at `~/.devnotes/notes.db`
(override the whole directory with the `DEVNOTES_HOME` env var, e.g.
to keep a notes DB per-project: `DEVNOTES_HOME=.devnotes devnotes
list`).

## Project layout

```
devnotes/
├── main.py           # single entry point — `python main.py` (GUI or CLI, no install needed)
├── devnotes/
│   ├── cli.py        # click commands — the CLI entry point
│   ├── gui.py         # tkinter desktop app — the GUI entry point
│   ├── highlight.py    # shared Pygments/Markdown highlighting for the GUI editor
│   ├── calendar_utils.py # date/grid math for the 45-day planner
│   ├── db.py          # SQLite schema + queries (shared by CLI and GUI)
│   ├── render.py       # rich rendering for the CLI, incl. code-block highlighting
│   ├── git_utils.py    # repo/branch auto-detection
│   ├── editor.py        # $EDITOR integration (CLI only)
│   ├── templates.py     # note templates (bug/todo/idea/...)
│   └── paths.py          # data-directory resolution
├── pyproject.toml
├── requirements.txt
└── README.md
```
