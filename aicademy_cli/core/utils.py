import shutil
import json
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from .. import config

console = Console()

def require_auth() -> str:
    token = config.get_token()
    if not token:
        console.print(
            "[red]✗ Not logged in.[/red] Run [bold]aicademy login[/bold] first."
        )
        raise typer.Exit(1)
    return token

def normalize_question_id(qid: str | None) -> str | None:
    """Zero-pad single-digit question IDs (e.g. cka-1 -> cka-01)"""
    if not qid:
        return qid
    parts = qid.split("-")
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 1:
        return f"{parts[0]}-0{parts[1]}"
    return qid

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
            table.add_row(t, f"aicademy install-tool {t}")
        console.print(table)
        console.print(
            f"\n[yellow]Run the install commands above, then retry.[/yellow]"
        )
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
