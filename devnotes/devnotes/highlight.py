"""Lightweight syntax highlighting for the Tk body editor.

Fenced code blocks (```lang ... ```) are tokenized with Pygments (if
installed) and colored per-token, monokai-ish. Everything outside
code fences gets cheap regex-based Markdown highlights (headers,
bold, inline code, checkboxes, #tags, bullets) — not a full Markdown
renderer, just enough to make the editor pleasant to write in.

Pygments is an optional dependency: if it's missing, code blocks
still get a distinct background so they're visually separated, they
just won't be colored token-by-token.
"""
from __future__ import annotations

import re

try:
    from pygments import lex
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.token import Token
    from pygments.util import ClassNotFound

    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

PALETTE = {
    "bg": "#1e1f22",
    "bg_alt": "#26282b",
    "fg": "#d4d4d4",
    "fg_dim": "#8a8f98",
    "accent": "#4fc1ff",
    "accent2": "#c586c0",
    "pin": "#ffcc66",
    "danger": "#f14c4c",
    "success": "#89d185",
    "border": "#3a3d41",
    "select": "#3a4b5c",
    "panel": "#242527",
}

TOKEN_COLORS = {}
if HAS_PYGMENTS:
    TOKEN_COLORS = {
        Token.Keyword: "#c586c0",
        Token.Keyword.Constant: "#569cd6",
        Token.Name.Function: "#dcdcaa",
        Token.Name.Class: "#4ec9b0",
        Token.Name.Builtin: "#4ec9b0",
        Token.Name.Decorator: "#dcdcaa",
        Token.Name.Tag: "#569cd6",
        Token.Name.Attribute: "#9cdcfe",
        Token.String: "#ce9178",
        Token.Number: "#b5cea8",
        Token.Comment: "#6a9955",
        Token.Operator: "#d4d4d4",
        Token.Punctuation: "#d4d4d4",
        Token.Text: "#d4d4d4",
        Token.Error: "#f14c4c",
    }

FENCE_RE = re.compile(r"```([\w+-]*)\n(.*?)```", re.DOTALL)
HEADER_RE = re.compile(r"^(#{1,6})\s+.*$", re.MULTILINE)
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
CHECKBOX_RE = re.compile(r"^-\s\[[ xX]\]\s.*$", re.MULTILINE)
TAGWORD_RE = re.compile(r"(?<!\w)#[A-Za-z0-9_-]+")
BULLET_RE = re.compile(r"^\s*[-*+]\s", re.MULTILINE)

_MD_TAGS = ["md_header", "md_bold", "md_inline_code", "md_checkbox", "md_tag", "md_bullet"]
_STRUCT_TAGS = ["code_block"] + _MD_TAGS


def configure_tags(text_widget) -> None:
    """Register every tag this module can apply. Call once after the
    Text widget is created, before the first highlight() call."""
    text_widget.tag_configure("code_block", background=PALETTE["bg_alt"])
    text_widget.tag_configure("md_header", foreground=PALETTE["accent"], font=("", 0, "bold"))
    text_widget.tag_configure("md_bold", font=("", 0, "bold"))
    text_widget.tag_configure(
        "md_inline_code", foreground=PALETTE["pin"], background=PALETTE["bg_alt"]
    )
    text_widget.tag_configure("md_checkbox", foreground=PALETTE["success"])
    text_widget.tag_configure("md_tag", foreground=PALETTE["accent"])
    text_widget.tag_configure("md_bullet", foreground=PALETTE["fg_dim"])

    if HAS_PYGMENTS:
        for token_type, color in TOKEN_COLORS.items():
            text_widget.tag_configure(f"tok_{token_type}", foreground=color)
        # code_block background must sit below token foreground tags
        text_widget.tag_lower("code_block")


def _guess_lexer(lang: str, code: str):
    if lang:
        try:
            return get_lexer_by_name(lang, stripnl=False)
        except ClassNotFound:
            pass
    try:
        return guess_lexer(code)
    except ClassNotFound:
        return None


def highlight(text_widget) -> None:
    """Re-scan the widget's full content and reapply all highlight tags.
    Safe to call repeatedly (e.g. on a debounce timer while typing)."""
    content = text_widget.get("1.0", "end-1c")

    for tag in _STRUCT_TAGS:
        text_widget.tag_remove(tag, "1.0", "end")
    if HAS_PYGMENTS:
        for token_type in TOKEN_COLORS:
            text_widget.tag_remove(f"tok_{token_type}", "1.0", "end")

    code_spans = []

    for match in FENCE_RE.finditer(content):
        lang = match.group(1)
        code = match.group(2)
        block_start = match.start(2)
        code_spans.append((match.start(), match.end()))

        text_widget.tag_add("code_block", f"1.0+{match.start()}c", f"1.0+{match.end()}c")

        if not HAS_PYGMENTS or not code.strip():
            continue
        lexer = _guess_lexer(lang, code)
        if lexer is None:
            continue
        try:
            tokens = list(lex(code, lexer))
        except Exception:
            continue
        offset = 0
        for token_type, value in tokens:
            length = len(value)
            if value.strip():
                t = token_type
                while t is not None and t not in TOKEN_COLORS:
                    t = t.parent
                if t is not None:
                    start = block_start + offset
                    end = start + length
                    text_widget.tag_add(f"tok_{t}", f"1.0+{start}c", f"1.0+{end}c")
            offset += length

    def outside_code(pos: int) -> bool:
        return not any(s <= pos < e for s, e in code_spans)

    for regex, tag in (
        (HEADER_RE, "md_header"),
        (BOLD_RE, "md_bold"),
        (INLINE_CODE_RE, "md_inline_code"),
        (CHECKBOX_RE, "md_checkbox"),
        (TAGWORD_RE, "md_tag"),
        (BULLET_RE, "md_bullet"),
    ):
        for m in regex.finditer(content):
            if outside_code(m.start()):
                text_widget.tag_add(tag, f"1.0+{m.start()}c", f"1.0+{m.end()}c")
