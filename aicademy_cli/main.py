"""Aicademy Practice CLI — Main Entry Point"""

import typer
from rich.console import Console
from rich.panel import Panel
from . import auth, question, tools
from .verify import app_verify

console = Console()

# ─── Main App ─────────────────────────────────────────────────────────────────
app = typer.Typer(
    name="aicademy",
    help="[bold cyan]Aicademy Practice CLI[/bold cyan] — Solve Kubernetes exam scenarios locally.",
    rich_markup_mode="rich",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

# ─── Command Groups ────────────────────────────────────────────────────────────
app.add_typer(auth.app, name="auth", help="Login, logout, and account management")
app.add_typer(question.app, name="question", help="Start, view instructions, and clean up practice sessions")
app.add_typer(tools.app, name="tools", help="Install required tools (kubectl, kind, docker)")

# ─── Top-level Shortcuts ───────────────────────────────────────────────────────

@app.command()
def login(
    token: str = typer.Option(None, "--token", "-t", help="Paste CLI token directly"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy login (same as aicademy auth login)"""
    auth.login(token=token)


@app.command()
def logout() -> None:
    """[bold]Shortcut:[/bold] aicademy logout (same as aicademy auth logout)"""
    auth.logout()


@app.command("install-tool")
def install_tool(
    tool: str = typer.Argument(..., help="kubectl | kind | docker | all"),
    check: bool = typer.Option(False, "--check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """[bold]Shortcut:[/bold] Install required tools using the system package manager."""
    tools.install(tool=tool, check=check, dry_run=dry_run)


@app.command()
def verify(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """
    Verify your solution for the current practice question.

    Runs verify.sh locally and reports the result to Aicademy.
    """
    app_verify(question_id=question_id)


# Welcome banner when --help is shown
def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import version, PackageNotFoundError
        try:
            v = version("aicademy-cli")
        except PackageNotFoundError:
            v = "dev"
        console.print(f"[bold cyan]aicademy-cli[/bold cyan] version [white]{v}[/white]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version"),
) -> None:
    """
    [bold cyan]Aicademy Practice CLI[/bold cyan]

    Practice CKA, CKAD, and CKS exam scenarios locally using KIND clusters.
    Full instructions and task verification happen right here in your terminal.

    [bold]Quick Start:[/bold]

      [green]aicademy login[/green]
      [green]aicademy install-tool all[/green]
      [green]aicademy question start cka-01[/green]
      [green]aicademy question instructions[/green]
      [green]aicademy verify[/green]
      [green]aicademy question clear[/green]

    [dim]More info: https://aicademy.ac/practice[/dim]
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
