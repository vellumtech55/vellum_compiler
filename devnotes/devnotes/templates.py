"""Pre-baked note skeletons — a small QOL win so you don't retype the
same structure every time you log a bug or a TODO."""

TEMPLATES = {
    "bug": (
        "## Steps to reproduce\n1. \n2. \n\n"
        "## Expected\n\n\n## Actual\n\n\n"
        "## Notes / stack trace\n```\n\n```\n"
    ),
    "todo": "- [ ] \n",
    "idea": "## Idea\n\n\n## Why it matters\n\n\n## Next step\n\n",
    "snippet": "```python\n\n```\n",
    "meeting": "## Attendees\n- \n\n## Discussion\n\n\n## Action items\n- [ ] \n",
    "decision": (
        "## Context\n\n\n## Decision\n\n\n## Alternatives considered\n\n\n"
        "## Consequences\n\n"
    ),
}


def get_template(name: str) -> str:
    return TEMPLATES.get(name, "")


def template_names() -> list[str]:
    return sorted(TEMPLATES.keys())
