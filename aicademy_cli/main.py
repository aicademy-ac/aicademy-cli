"""Aicademy Practice CLI — Main Entry Point"""

from __future__ import annotations

import typer
from rich.console import Console

from . import auth as auth_flow
from .commands import auth, legacy, question, tools
from .commands.verify import app_verify

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
app.add_typer(
    question.app, name="question", help="Start, view instructions, and clean up practice sessions"
)
app.add_typer(
    tools.app, name="tools", help="Install and check required tools (kubectl, kind, docker)"
)
app.add_typer(legacy.app, name="legacy", help="Deprecated commands")

# ─── Top-level Shortcuts ───────────────────────────────────────────────────────


@app.command()
def login(
    token: str = typer.Option(None, "--token", "-t", help="Paste CLI token directly"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed poll status"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy login (same as aicademy auth login)"""
    import asyncio

    asyncio.run(auth_flow.perform_login(token, verbose=verbose))


@app.command()
def logout() -> None:
    """[bold]Shortcut:[/bold] aicademy logout (same as aicademy auth logout)"""
    import asyncio

    asyncio.run(auth_flow.logout_user())


@app.command()
def whoami() -> None:
    """[bold]Shortcut:[/bold] aicademy whoami (same as aicademy auth whoami)"""
    import asyncio

    asyncio.run(auth_flow.whoami())


@app.command("install-tool")
def install_tool(
    tool: str = typer.Argument(..., help="kubectl | kind | docker | all"),
    check: bool = typer.Option(False, "--check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """[bold]Shortcut:[/bold] [DEPRECATED] Use `aicademy tools --install` instead."""
    console.print(
        "[yellow]⚠ `aicademy install-tool` is deprecated. "
        "Use [bold]aicademy tools --install[/bold] instead.[/yellow]"
    )
    legacy.install_tool(tool=tool, check=check, dry_run=dry_run)


@app.command()
def verify(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """
    Verify your solution for the current practice question.
    """
    app_verify(question_id=question_id)


@app.command("list")
def list_questions() -> None:
    """[bold]Shortcut:[/bold] aicademy list (same as aicademy question list)"""
    question.list_questions()


@app.command("ls")
def list_questions_short() -> None:
    """[bold]Shortcut:[/bold] aicademy ls (same as aicademy question list)"""
    question.list_questions()


@app.command()
def start(
    question_id: str = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy start (same as aicademy question start)"""
    question.start(question_id=question_id, verbose=verbose)


@app.command()
def launch(
    question_id: str = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy launch (same as aicademy question start)"""
    question.start(question_id=question_id, verbose=verbose)


@app.command()
def instructions(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
    web: bool = typer.Option(False, "--web", help="Open the question page in browser instead"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy instructions (same as aicademy question instructions)"""
    question.instructions(question_id=question_id, web=web)


@app.command()
def clear(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy clear (same as aicademy question clear)"""
    question.clear(question_id=question_id, verbose=verbose)


# Welcome banner when --help is shown
def _version_callback(value: bool) -> None:
    if value:
        from importlib.metadata import PackageNotFoundError, version

        try:
            v = version("aicademy")
        except PackageNotFoundError:
            v = "dev"
        console.print(f"[bold cyan]aicademy[/bold cyan] version [white]{v}[/white]")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None, "--version", "-V", callback=_version_callback, is_eager=True, help="Show version"
    ),
) -> None:
    """
    [bold cyan]Aicademy Practice CLI[/bold cyan]

    Practice CKA, CKAD, and CKS exam scenarios locally using KIND clusters.
    Full instructions and task verification happen right here in your terminal.

    [bold]Quick Start:[/bold]

      [green]aicademy login[/green]
      [green]aicademy tools --install[/green]
      [green]aicademy start cka-01[/green]
      [green]aicademy instructions[/green]
      [green]aicademy verify[/green]
      [green]aicademy clear[/green]

    [dim]More info: https://aicademy.ac/practice[/dim]
    """
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
