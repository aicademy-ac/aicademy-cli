"""Interactive question picker.

`questionary` renders a genuinely scrollable, arrow-key-navigable list
natively -- no manual "10 per page, press n/p" pagination needed, and
`use_search_filter` lets the user type to narrow a long list on top of
that. This is the one place in the CLI that steps outside the plain
Rich-prompt style used everywhere else, by deliberate choice: browsing
~300 questions by free-typing an exact ID doesn't scale.
"""

from __future__ import annotations

from typing import Any

_CATEGORY_CHOICES: list[tuple[str, str]] = [
    ("cka", "CKA — Certified Kubernetes Administrator"),
    ("ckad", "CKAD — Certified Kubernetes Application Developer"),
    ("cks", "CKS — Certified Kubernetes Security Specialist"),
]


def _status_glyph(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "·"
    if entry.get("passed"):
        return "✓"
    if entry.get("status") == "active":
        return "▸"
    return "·"


_ALL_CATEGORIES_SENTINEL = "__all__"


async def pick_category() -> str | None:
    """Prompt for a category. Returns a slug (cka/ckad/cks), or None for
    "all categories" -- also None if the user cancels (Ctrl+C/Esc), which
    callers should treat the same as "no filter" rather than an error."""
    import questionary

    # questionary.Choice(value=None) doesn't actually keep the value as
    # None -- it falls back to using the title as the value instead, which
    # would silently turn "All categories" into a (wrong) category filter.
    # A real sentinel avoids that, converted back to None below.
    choices = [questionary.Choice(title=label, value=slug) for slug, label in _CATEGORY_CHOICES]
    choices.append(questionary.Choice(title="All categories", value=_ALL_CATEGORIES_SENTINEL))
    # .ask_async() (not .ask()) -- this runs inside a CLI command already
    # driven by asyncio.run(), and .ask() internally calls asyncio.run()
    # itself, which blows up with "cannot be called from a running event
    # loop". .ask_async() awaits on the existing loop instead.
    result = await questionary.select("Which exam?", choices=choices).ask_async()
    return None if result in (None, _ALL_CATEGORIES_SENTINEL) else result


async def pick_question(
    questions: list[dict[str, Any]],
    progress: dict[str, Any],
    message: str = "Pick a question (type to search, ↑/↓ to move, Enter to select):",
) -> str | None:
    """Scrollable, searchable arrow-key list of questions.

    Returns the chosen question ID, or None if the list was empty or the
    user cancelled (Ctrl+C/Esc) -- callers should treat both as "nothing
    selected", not an error.
    """
    import questionary

    choices = []
    for q in questions:
        qid = str(q.get("id", ""))
        glyph = _status_glyph(progress.get(qid))
        title = (
            f"{glyph}  {qid:<10} {str(q.get('title', ''))[:45]:<45} "
            f"{str(q.get('level', '')).capitalize()}"
        )
        choices.append(questionary.Choice(title=title, value=qid))
    if not choices:
        return None
    return await questionary.select(message, choices=choices, use_search_filter=True).ask_async()
