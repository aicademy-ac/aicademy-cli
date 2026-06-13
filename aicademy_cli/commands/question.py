"""Practice question commands — start, instructions, clear"""

import typer
import webbrowser
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from .. import config, api
from ..core import utils, kind

console = Console()
app = typer.Typer(help="Manage practice question sessions")

@app.command()
def start(
    question_id: str = typer.Argument(..., help="Question ID to start, e.g. cka-01"),
) -> None:
    """
    Start a practice question environment.
    """
    utils.require_auth()
    question_id = utils.normalize_question_id(question_id)

    if not utils.check_prerequisites():
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting question [white]{question_id}[/white]...[/bold cyan]")
    cluster_name = f"aicademy-{question_id}"

    # Start the session via API
    try:
        data = api.start_session(question_id, cluster_name)
    except api.APIError as e:
        if e.status_code in (402, 409):
            utils.format_access_error(e)
        else:
            console.print(f"[red]✗ API error ({e.status_code}): {e.response_data}[/red]")
        raise typer.Exit(1)

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
    kind.create_cluster(cluster_name)

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
    """Show full question instructions in the terminal."""
    utils.require_auth()

    session = config.get_active_session()
    if not session and not question_id:
        console.print(
            "[red]✗ No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    qid = utils.normalize_question_id(question_id) or session.get("questionId")

    if web:
        cat = session.get("category", "") if session else ""
        url = f"{config.API_BASE_URL}/practice/{cat}/{qid}"
        console.print(f"[cyan]Opening:[/cyan] {url}")
        webbrowser.open(url)
        raise typer.Exit()

    # Fetch full question from API
    session_data = config.get_active_session() or {}
    cat = session_data.get("category", qid.split("-")[0] if qid else "")
    
    try:
        data = api.get_question(cat, qid)
    except api.APIError as e:
        if e.status_code == 403:
            console.print(
                "[red]✗ No active session found for this question.[/red]\n"
                f"Run: [bold]aicademy question start {qid}[/bold]"
            )
        else:
            console.print(f"[red]✗ {e.status_code}: {e.response_data}[/red]")
        raise typer.Exit(1)

    q = data.get("question", {})
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

    if q.get("scenario"):
        console.print("\n[bold]Scenario[/bold]")
        console.print(Markdown(q["scenario"]))

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
    """Clean up the practice environment."""
    utils.require_auth()

    question_id = utils.normalize_question_id(question_id)
    session = config.get_active_session()
    if not session and not question_id:
        console.print("[yellow]No active session found.[/yellow]")
        raise typer.Exit()

    session_id = (session or {}).get("sessionId")
    cluster_name = (session or {}).get("clusterName") or f"aicademy-{question_id}"

    # Delete KIND cluster
    kind.delete_cluster(cluster_name)

    # Mark session as abandoned via API
    if session_id:
        api.abandon_session(session_id)

    config.set_active_session(None)
    console.print(
        Panel(
            "[bold green]✓ Environment cleaned up.[/bold green]\n\n"
            "You can now start a new question with:\n"
            "[bold]aicademy question start <question-id>[/bold]",
            border_style="green",
        )
    )
