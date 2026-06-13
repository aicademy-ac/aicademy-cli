"""Practice question commands — start, instructions, clear"""

import subprocess
import shutil
import json
import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import box
from . import config

console = Console()
app = typer.Typer(help="Manage practice question sessions")

API_HEADERS = lambda: {"Authorization": f"Bearer {config.get_token()}"}  # noqa: E731


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


def format_access_error(error_body: str) -> None:
    """Parse and display a structured API error (upgrade required, session conflict, etc.)"""
    try:
        err = json.loads(error_body)
        code = err.get("code", "")

        if code == "UPGRADE_REQUIRED":
            benefits = "\n".join(f"  ✦ {b}" for b in err.get("benefits", []))
            console.print(
                Panel(
                    f"[bold red]Access Denied — Pro Plan Required[/bold red]\n\n"
                    f"{err.get('message', '')}\n\n"
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
                    f"{err.get('message', '')}\n\n"
                    f"[bold]Active Question:[/bold] {err.get('activeQuestionId', 'unknown')}",
                    title="⚠  Session Conflict",
                    border_style="yellow",
                )
            )
        else:
            console.print(f"[red]Error: {error_body}[/red]")
    except (json.JSONDecodeError, KeyError):
        console.print(f"[red]Error: {error_body}[/red]")


@app.command()
def start(
    question_id: str = typer.Argument(..., help="Question ID to start, e.g. cka-01"),
) -> None:
    """
    Start a practice question environment.

    This command:
    1. Checks that docker, kubectl, and kind are installed
    2. Starts a session via the Aicademy API
    3. Creates a KIND cluster using the question's kind.yaml
    4. Prints session info and next steps
    """
    require_auth()

    question_id = normalize_question_id(question_id)

    if not check_prerequisites():
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting question [white]{question_id}[/white]...[/bold cyan]")


    cluster_name = f"aicademy-{question_id}"

    # Start the session via API
    try:
        resp = httpx.post(
            f"{config.API_BASE_URL}/api/practice/sessions",
            json={"questionId": question_id, "clusterName": cluster_name},
            headers=API_HEADERS(),
            timeout=15,
        )
    except httpx.RequestError as exc:
        console.print(f"[red]✗ Network error: {exc}[/red]")
        raise typer.Exit(1)

    if resp.status_code == 402:
        format_access_error(resp.text)
        raise typer.Exit(1)

    if resp.status_code == 409:
        format_access_error(resp.text)
        raise typer.Exit(1)

    if resp.status_code not in (200, 201):
        console.print(f"[red]✗ API error ({resp.status_code}): {resp.text}[/red]")
        raise typer.Exit(1)

    data = resp.json()
    session = data
    question = data.get("question", {})

    # Cache session locally
    config.set_active_session(
        {
            "sessionId": session.get("sessionId"),
            "questionId": question_id,
            "clusterName": cluster_name,
            "category": question.get("category", ""),
        }
    )

    # Create KIND cluster
    console.print(f"\n[bold]Creating KIND cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    console.print("[dim]This may take 30–90 seconds...[/dim]\n")

    kind_cmd = ["kind", "create", "cluster", "--name", cluster_name]
    try:
        subprocess.run(kind_cmd, check=True)
    except subprocess.CalledProcessError:
        console.print("[red]✗ Failed to create KIND cluster.[/red]")
        console.print("[dim]Make sure Docker is running.[/dim]")
        raise typer.Exit(1)

    # Print success panel
    console.print(
        Panel(
            f"[bold green]✓ Environment Ready![/bold green]\n\n"
            f"[bold]Question:[/bold]  {question.get('title', question_id)}\n"
            f"[bold]Level:[/bold]     {question.get('level', '').capitalize()}\n"
            f"[bold]Category:[/bold]  {question.get('category', '').upper()}\n"
            f"[bold]Cluster:[/bold]   {cluster_name}\n"
            f"[bold]Time:[/bold]      ~{question.get('estimatedMinutes', '?')} minutes\n\n"
            "[bold]Next steps:[/bold]\n"
            "  [cyan]aicademy question instructions[/cyan]  — read full tasks\n"
            "  [cyan]aicademy verify[/cyan]                 — check your solution\n"
            "  [cyan]aicademy question clear[/cyan]         — clean up when done",
            title="🚀  Session Started",
            border_style="green",
        )
    )


@app.command()
def instructions(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
    web: bool = typer.Option(False, "--web", help="Open the question page in browser instead"),
) -> None:
    """
    Show full question instructions in the terminal.

    Requires an active session started with: aicademy question start <id>

    Use --web to open the question page in your browser instead.
    """
    require_auth()

    session = config.get_active_session()
    if not session and not question_id:
        console.print(
            "[red]✗ No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    qid = normalize_question_id(question_id) or session.get("questionId")

    if web:
        import webbrowser
        cat = session.get("category", "") if session else ""
        url = f"{config.API_BASE_URL}/practice/{cat}/{qid}"
        console.print(f"[cyan]Opening:[/cyan] {url}")
        webbrowser.open(url)
        raise typer.Exit()

    # Fetch full question from API (requires active session)
    try:
        session_data = config.get_active_session() or {}
        cat = session_data.get("category", qid.split("-")[0] if qid else "")
        resp = httpx.get(
            f"{config.API_BASE_URL}/api/practice/questions/{cat}/{qid}",
            headers=API_HEADERS(),
            timeout=10,
        )
    except httpx.RequestError as exc:
        console.print(f"[red]✗ Network error: {exc}[/red]")
        raise typer.Exit(1)

    if resp.status_code == 403:
        console.print(
            "[red]✗ No active session found for this question.[/red]\n"
            f"Run: [bold]aicademy question start {qid}[/bold]"
        )
        raise typer.Exit(1)

    if resp.status_code != 200:
        console.print(f"[red]✗ {resp.status_code}: {resp.text}[/red]")
        raise typer.Exit(1)

    q = resp.json().get("question", {})
    tasks = q.get("tasks", [])
    hints = q.get("hints", [])

    console.print(
        Panel(
            f"[bold]{q.get('title', '')}[/bold]\n\n"
            f"[dim]Category:[/dim] {q.get('category', '').upper()}  "
            f"[dim]Level:[/dim] {q.get('level', '').capitalize()}  "
            f"[dim]Time:[/dim] ~{q.get('estimatedMinutes', '?')}m",
            title=f"📋  Question {qid}",
            border_style="cyan",
        )
    )

    # Scenario
    if q.get("scenario"):
        console.print("\n[bold]Scenario[/bold]")
        console.print(Markdown(q["scenario"]))

    # Tasks
    if tasks:
        console.print("\n[bold]Tasks[/bold]")
        for i, task in enumerate(tasks, 1):
            console.print(
                Panel(
                    f"[bold]{task.get('title', '')}[/bold]\n\n{task.get('description', '')}",
                    title=f"Task {i}",
                    border_style="dim",
                )
            )

    # Hints
    if hints:
        console.print("\n[bold dim]Hints (expand if stuck)[/bold dim]")
        for hint in hints:
            console.print(f"  [dim]→ {hint}[/dim]")

    console.print(
        f"\n[dim]When done:[/dim] [bold]aicademy verify[/bold]  |  "
        "[dim]To clean up:[/dim] [bold]aicademy question clear[/bold]"
    )


@app.command()
def clear(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """
    Clean up the practice environment.

    Deletes the KIND cluster and marks the session as abandoned.
    """
    require_auth()

    question_id = normalize_question_id(question_id)
    session = config.get_active_session()
    if not session and not question_id:
        console.print("[yellow]No active session found.[/yellow]")
        raise typer.Exit()

    session_id = (session or {}).get("sessionId")
    cluster_name = (session or {}).get("clusterName") or f"aicademy-{question_id}"

    # Delete KIND cluster
    console.print(f"[bold]Deleting cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    try:
        subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=True)
        console.print("[green]✔ Cluster deleted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠ Could not delete cluster (may not exist).[/yellow]")

    # Mark session as abandoned via API
    if session_id:
        try:
            httpx.patch(
                f"{config.API_BASE_URL}/api/practice/sessions/{session_id}",
                headers=API_HEADERS(),
                timeout=10,
            )
        except httpx.RequestError:
            pass

    config.set_active_session(None)
    console.print(
        Panel(
            "[bold green]✓ Environment cleaned up.[/bold green]\n\n"
            "You can now start a new question with:\n"
            "[bold]aicademy question start <question-id>[/bold]",
            border_style="green",
        )
    )


# Re-export as `question` group alias in main
