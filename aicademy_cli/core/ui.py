"""Boxless message blocks -- a lighter alternative to `rich.panel.Panel`.

A bold colored heading line plus a thin rule reads as "one visual unit"
without needing a border, keeping output scannable without the heavier
box-drawing look. `style` picks both the heading color and the rule color,
so callers get one consistent color per message (green=success,
red=error, yellow=warning, cyan=info) matching how borders were used before.
"""

from __future__ import annotations

from rich.console import Console, RenderableType

_RULE_MIN_WIDTH = 20
_RULE_MAX_WIDTH = 60


def print_block(
    console: Console,
    title: str,
    body: RenderableType,
    *,
    style: str = "cyan",
) -> None:
    """Print a title + underline + body block.

    The underline is sized to the title (not the full terminal width, which
    `rich.rule.Rule` always fills) -- a tighter, markdown-heading feel
    instead of a wide line dangling under a short title. `body` can be a
    plain string (with its own Rich markup) or any Rich renderable (e.g.
    `rich.markdown.Markdown`).
    """
    console.print(f"\n[bold {style}]{title}[/bold {style}]")
    width = min(max(len(title), _RULE_MIN_WIDTH), _RULE_MAX_WIDTH)
    console.print(f"[{style}]{'─' * width}[/{style}]")
    console.print(body)
