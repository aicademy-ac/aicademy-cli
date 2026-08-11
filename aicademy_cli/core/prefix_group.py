"""Unique-prefix command abbreviation for the root Typer app.

Lets `aicademy la` resolve to `launch`, `aicademy v` to `verify`, etc. --
matched dynamically against whatever commands are currently registered, so
it can never drift out of sync with the command list and needs no
hardcoded aliases. An ambiguous prefix (e.g. bare `l`, matching `login`,
`list`, `ls`, `launch`, `logout`) reports its candidates instead of
guessing; anything else falls through to Typer's normal resolution
(including its existing "did you mean" typo-suggestion behavior).

Applied only at the root app (`typer.Typer(cls=PrefixMatchingGroup)`) --
sub-apps (`auth`, `question`, `tools`, `config`) keep Typer's default
resolution unless individually opted in.
"""

from __future__ import annotations

from typing import Any

from typer.core import TyperGroup


class PrefixMatchingGroup(TyperGroup):
    # `ctx` is typed `Any`, not `typer.Context`: the base class's own
    # `resolve_command` takes typer's private `_click.Context`, and
    # `typer.Context` is a *subclass* of that -- annotating it here would
    # narrow the parameter type and violate Liskov substitution (mypy
    # correctly flags this as an incompatible override).
    def resolve_command(self, ctx: Any, args: list[str]) -> tuple[str | None, Any, list[str]]:
        if args and not args[0].startswith("-") and self.get_command(ctx, args[0]) is None:
            typed = args[0]
            matches = sorted(name for name in self.list_commands(ctx) if name.startswith(typed))
            if len(matches) == 1:
                args = [matches[0], *args[1:]]
            elif len(matches) > 1:
                ctx.fail(
                    f"{typed!r} is ambiguous: could mean {', '.join(matches)}. "
                    "Type more letters to narrow it down."
                )
        return super().resolve_command(ctx, args)
