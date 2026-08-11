"""Deprecated top-level commands."""

from __future__ import annotations

import typer
from rich.console import Console

from ..core.prefix_group import PrefixMatchingGroup
from .tools import install_legacy_tool

console = Console()
app = typer.Typer(
    help="Deprecated commands (use `aicademy tools` instead)", cls=PrefixMatchingGroup
)


@app.command("install-tool")
def install_tool(
    tool: str = typer.Argument(..., help="kubectl | kind | docker | all"),
    check: bool = typer.Option(False, "--check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """
    [DEPRECATED] Use `aicademy tools --install` instead.
    """
    console.print(
        "[yellow]⚠ `aicademy install-tool` is deprecated. "
        "Use [bold]aicademy tools --install[/bold] instead.[/yellow]"
    )
    install_legacy_tool(tool=tool, check=check, dry_run=dry_run)
