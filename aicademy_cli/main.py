"""Aicademy Practice CLI — Main Entry Point"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

from . import config, state
from .commands import auth, legacy, question, settings, tools
from .commands.verify import app_verify
from .core.prefix_group import PrefixMatchingGroup

console = Console()

# ─── Main App ─────────────────────────────────────────────────────────────────
app = typer.Typer(
    name="aicademy",
    help=(
        "[bold cyan]Aicademy Practice CLI[/bold cyan] — "
        "Solve Kubernetes exam scenarios locally.\n\n"
        "[dim]Commands can be abbreviated to their shortest unique prefix, "
        "e.g. [bold]aicademy la[/bold] for [bold]launch[/bold].[/dim]"
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    cls=PrefixMatchingGroup,
)

# ─── Command Groups ────────────────────────────────────────────────────────────
app.add_typer(auth.app, name="auth", help="Login, logout, and account management")
app.add_typer(
    question.app, name="question", help="Start, view instructions, and clean up practice sessions"
)
app.add_typer(
    tools.app, name="tools", help="Install and check required tools (kubectl, kind, docker)"
)
app.add_typer(legacy.app, name="legacy", help="Deprecated commands", hidden=True)
app.add_typer(settings.app, name="config", help="View and change CLI preferences")

# ─── Top-level Shortcuts ───────────────────────────────────────────────────────


@app.command()
def login(
    token: str = typer.Option(
        None,
        "--token",
        "-t",
        help="Paste a CLI token directly (skip browser flow). Insecure: leaks to shell history.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed poll status"),
) -> None:
    """[bold]Shortcut:[/bold] aicademy login (same as aicademy auth login)"""
    auth.login(token=token, verbose=verbose)


@app.command()
def logout() -> None:
    """[bold]Shortcut:[/bold] aicademy logout (same as aicademy auth logout)"""
    auth.logout()


@app.command()
def whoami() -> None:
    """[bold]Shortcut:[/bold] aicademy whoami (same as aicademy auth whoami)"""
    auth.whoami()


@app.command("install-tool", hidden=True)
def install_tool(
    tool: str = typer.Argument(..., help="kubectl | kind | docker | all"),
    check: bool = typer.Option(False, "--check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """[DEPRECATED] Use `aicademy tools --install` instead."""
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
def list_questions(
    cka: bool = question._CKA_OPT,
    ckad: bool = question._CKAD_OPT,
    cks: bool = question._CKS_OPT,
    beginner: bool = question._BEGINNER_OPT,
    intermediate: bool = question._INTERMEDIATE_OPT,
    advanced: bool = question._ADVANCED_OPT,
    expert: bool = question._EXPERT_OPT,
) -> None:
    """[bold]Shortcut:[/bold] aicademy list (same as aicademy question list)"""
    question.list_questions(cka, ckad, cks, beginner, intermediate, advanced, expert)


@app.command("ls")
def list_questions_short(
    cka: bool = question._CKA_OPT,
    ckad: bool = question._CKAD_OPT,
    cks: bool = question._CKS_OPT,
    beginner: bool = question._BEGINNER_OPT,
    intermediate: bool = question._INTERMEDIATE_OPT,
    advanced: bool = question._ADVANCED_OPT,
    expert: bool = question._EXPERT_OPT,
) -> None:
    """[bold]Shortcut:[/bold] aicademy ls (same as aicademy question list)"""
    question.list_questions(cka, ckad, cks, beginner, intermediate, advanced, expert)


@app.command()
def start(
    question_id: str = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
    cka: bool = question._CKA_OPT,
    ckad: bool = question._CKAD_OPT,
    cks: bool = question._CKS_OPT,
    beginner: bool = question._BEGINNER_OPT,
    intermediate: bool = question._INTERMEDIATE_OPT,
    advanced: bool = question._ADVANCED_OPT,
    expert: bool = question._EXPERT_OPT,
) -> None:
    """[bold]Shortcut:[/bold] aicademy start (same as aicademy question start)"""
    question.start(question_id, verbose, cka, ckad, cks, beginner, intermediate, advanced, expert)


@app.command()
def launch(
    question_id: str = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
    cka: bool = question._CKA_OPT,
    ckad: bool = question._CKAD_OPT,
    cks: bool = question._CKS_OPT,
    beginner: bool = question._BEGINNER_OPT,
    intermediate: bool = question._INTERMEDIATE_OPT,
    advanced: bool = question._ADVANCED_OPT,
    expert: bool = question._EXPERT_OPT,
) -> None:
    """[bold]Shortcut:[/bold] aicademy launch (same as aicademy question start)"""
    question.launch(question_id, verbose, cka, ckad, cks, beginner, intermediate, advanced, expert)


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
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full internal detail (subprocess output, tracebacks) instead of a clean summary",
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
    if verbose:
        state.set_verbose(True)
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


# Flags that mean "just print one thing and exit" -- scripts and CI parse
# their output directly, so the first-run telemetry notice must never inject
# an extra line ahead of it (e.g. `aicademy --version` piped into a version
# check). No subcommand at all is bare `--help` too (no_args_is_help=True).
_SILENT_ARGV_FLAGS = {"--version", "-V", "--help", "-h"}


def _maybe_show_error_reporting_notice(argv: list[str]) -> None:
    if not argv or any(flag in _SILENT_ARGV_FLAGS for flag in argv):
        return
    if config.error_reporting_notice_shown():
        return
    config.mark_error_reporting_notice_shown()
    if not config.is_error_reporting_enabled():
        return
    # stderr, not the shared stdout console: this is a side-channel notice,
    # not command output, and must never end up in `aicademy list | ...`.
    Console(stderr=True).print(
        "[dim]Aicademy CLI sends anonymous crash reports to help fix bugs faster. "
        "Disable anytime: [bold]aicademy config error-reporting off[/bold][/dim]\n"
    )


def _ensure_utf8_stdio() -> None:
    """Force UTF-8 on stdout/stderr, replacing anything unencodable.

    Windows consoles default to the OS codepage (often cp1252), which can't
    encode the checkmarks/arrows Rich prints throughout this CLI --
    crashing every command with UnicodeEncodeError on a stock `cmd.exe` or
    older PowerShell. `errors="replace"` guarantees output never crashes,
    even on a genuinely broken terminal; it just substitutes '?' for
    anything unencodable rather than taking the whole command down.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass


def _write_crash_log(exc: BaseException) -> Path:
    """Append the full traceback to a log file, regardless of --verbose --
    the console output may be sanitized, but the detail is never lost.
    Best-effort: a logging failure must never mask the original error.
    """
    import traceback
    from datetime import datetime, timezone

    log_path = config.CONFIG_DIR / "aicademy.log"
    try:
        config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {timestamp} ---\n{formatted}")
    except Exception:
        pass
    return log_path


def cli_entry() -> None:
    """Console-script entry point (see [project.scripts] in pyproject.toml).

    Wraps `app()` so unexpected crashes get reported -- subject to the user's
    error-reporting preference -- before propagating normally. `SystemExit`
    (Typer/Click's own exit-code signaling) is a `BaseException`, not an
    `Exception`, so well-behaved `typer.Exit()` calls pass through untouched.
    Ctrl+C gets its own clean message instead of a raw Python traceback.

    Unhandled exceptions are always fully logged to disk; the console only
    gets a Python traceback when the user explicitly asked for it via
    --verbose. Otherwise they get one clean line and a pointer to the log.
    """
    _ensure_utf8_stdio()
    _maybe_show_error_reporting_notice(sys.argv[1:])
    try:
        app()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Interrupted.[/yellow]")
        # sys.exit, not typer.Exit: we're past Click's own exception handling
        # here (app() already returned/raised), so nothing else would catch
        # a click.exceptions.Exit and turn it into a clean process exit.
        sys.exit(130)  # 128 + SIGINT, the conventional exit code
    except Exception as exc:
        from .error_reporting import report_error_sync

        command = sys.argv[1] if len(sys.argv) > 1 else None
        report_error_sync(exc, command=command)
        log_path = _write_crash_log(exc)
        if state.is_verbose():
            raise  # Typer's own pretty-exception rendering shows the full traceback
        console.print(f"[red]✗ Something went wrong: {exc}[/red]")
        console.print(
            f"[dim]Details logged to {log_path}. Re-run with --verbose for the full error.[/dim]"
        )
        sys.exit(1)


if __name__ == "__main__":
    cli_entry()
