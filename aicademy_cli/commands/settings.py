"""CLI-local preferences: error-reporting opt-out and shell alias installer."""

from __future__ import annotations

import typer
from rich.console import Console

from .. import config
from ..core import shell_alias
from ..core.prefix_group import PrefixMatchingGroup

console = Console()
app = typer.Typer(help="View and change CLI preferences", cls=PrefixMatchingGroup)


@app.command("show")
def show_settings() -> None:
    """Show current CLI settings."""
    state = "on" if config.is_error_reporting_enabled() else "off"
    console.print(f"[bold]Error reporting:[/bold] {state}")


@app.command("error-reporting")
def set_error_reporting(
    state: str = typer.Argument(..., help="on | off"),
) -> None:
    """Enable or disable anonymous crash reporting."""
    normalized = state.strip().lower()
    if normalized not in ("on", "off"):
        console.print("[red]✗ Expected 'on' or 'off'.[/red]")
        raise typer.Exit(1)
    config.set_error_reporting(normalized == "on")
    console.print(f"[bold green]✓ Error reporting turned {normalized}.[/bold green]")


_MANUAL_INSTRUCTIONS = (
    "bash/zsh:   alias aic='aicademy'   alias k='kubectl'\n"
    "fish:       alias aic 'aicademy'   alias k 'kubectl'\n"
    "PowerShell: Set-Alias aic aicademy   Set-Alias k kubectl"
)


@app.command("install-aliases")
def install_aliases() -> None:
    """Add 'aic' (aicademy) and 'k' (kubectl) shortcuts to your shell config."""
    shell, results = shell_alias.install_aliases()

    if shell is None:
        console.print("[yellow]⚠ Could not detect your shell.[/yellow] Add these manually:\n")
        console.print(_MANUAL_INSTRUCTIONS)
        raise typer.Exit(1)

    if not results:
        console.print(
            f"[yellow]⚠ '{shell}' isn't a supported shell for auto-install.[/yellow] "
            "Add these manually:\n"
        )
        console.print(_MANUAL_INSTRUCTIONS)
        raise typer.Exit(1)

    console.print(f"[dim]Detected shell: {shell}[/dim]\n")
    for result in results:
        if result.status == "added":
            console.print(
                f"[green]✓[/green] {result.name} → {result.target}  [dim]({result.detail})[/dim]"
            )
        elif result.status == "already present":
            console.print(f"[dim]· {result.name} already present in {result.detail}[/dim]")
        else:
            console.print(f"[red]✗ {result.name}: {result.detail}[/red]")

    if any(r.status == "added" for r in results):
        console.print("\n[dim]Restart your shell (or re-source your profile) to use them.[/dim]")
