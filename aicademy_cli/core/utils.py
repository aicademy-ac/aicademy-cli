from __future__ import annotations

import json
import re
import shutil

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .. import config

console = Console()

_QID_RE = re.compile(
    r"^(?P<prefix>cka|ckad|a|c|d)-?(?P<num>\d+)$",
    re.IGNORECASE,
)


def escape_rich_markup(text: str) -> str:
    """Escape Rich markup brackets to prevent accidental formatting."""
    return text.replace("[", "\\[").replace("]", "\\]")


def require_auth() -> str:
    token = config.get_token()
    if not token:
        console.print("[red]✗ Not logged in.[/red] Run [bold]aicademy login[/bold] first.")
        raise typer.Exit(1)
    return token


def normalize_question_id(qid: str | None) -> str | None:
    """
    Normalize question IDs to the canonical form.

    Supported aliases:
      cka-1, cka-01, cka01, cka1, a1, a-1   -> cka-01
      cka-12, cka12, a12                     -> cka-12
      ckad-3, ckad-03, ckad03, c3, d3        -> ckad-03
    """
    if not qid:
        return qid

    m = _QID_RE.match(qid.strip())
    if not m:
        return qid

    prefix = m.group("prefix").lower()
    num = int(m.group("num"))
    canonical_prefix = {"a": "cka", "c": "ckad", "d": "ckad"}.get(prefix, prefix)
    return f"{canonical_prefix}-{num:02d}"


def check_prerequisites() -> bool:
    """Check that docker, kind, and kubectl are installed."""
    missing = []
    for tool in ["docker", "kind", "kubectl"]:
        if not shutil.which(tool):
            missing.append(tool)

    if missing:
        table = Table(title="⚠ Missing Prerequisites", border_style="yellow", box=box.ROUNDED)
        table.add_column("Tool", style="bold")
        table.add_column("Install Command")
        for t in missing:
            table.add_row(t, "aicademy tools --install")
        console.print(table)
        console.print("\n[yellow]Run the install commands above, then retry.[/yellow]")
        return False
    return True


def format_access_error(e: Exception) -> None:
    """Parse and display a structured API error (upgrade required, session conflict, etc.)"""
    from ..api import APIError

    error_body = e.response_data if isinstance(e, APIError) else str(e)
    if isinstance(error_body, str):
        try:
            err = json.loads(error_body)
        except (json.JSONDecodeError, TypeError):
            err = {}
    else:
        err = error_body or {}

    if isinstance(err, dict) and "message" in err:
        try:
            inner_err = json.loads(err["message"])
            if isinstance(inner_err, dict):
                err = inner_err
        except Exception:
            pass

    code = err.get("code", "")
    message = err.get("message", str(error_body) if error_body else str(e))

    if code == "UPGRADE_REQUIRED":
        benefits = "\n".join(f"  ✦ {b}" for b in err.get("benefits", []))
        console.print(
            Panel(
                f"[bold red]Access Denied — Pro Plan Required[/bold red]\n\n"
                f"{message}\n\n"
                f"[bold]Pro Plan Benefits:[/bold]\n{benefits}\n\n"
                f"[bold cyan]Upgrade at:[/bold cyan] {err.get('upgradeUrl', 'https://aicademy.ac/practice#pricing')}",
                title="💳  Upgrade Required",
                border_style="red",
            )
        )
    elif code == "SESSION_ACTIVE":
        console.print(
            Panel(
                f"[bold yellow]Active Session Exists[/bold yellow]\n\n"
                f"{message}\n\n"
                f"[bold]Active Question:[/bold] {err.get('activeQuestionId', 'unknown')}",
                title="⚠  Session Conflict",
                border_style="yellow",
            )
        )
    else:
        console.print(f"[red]Error: {message}[/red]")
