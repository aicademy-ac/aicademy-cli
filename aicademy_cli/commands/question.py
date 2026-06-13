"""Practice question commands — start, instructions, clear"""

import typer
import webbrowser
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import box
from rich.prompt import Prompt
from .. import config, api
from ..core import utils, kind

console = Console()
app = typer.Typer(help="Manage practice question sessions")

@app.command("list")
def list_questions() -> None:
    """List all available questions and your progress."""
    utils.require_auth()
    try:
        data = api.get_all_questions()
    except api.APIError as e:
        console.print(f"[red]✗ Failed to load questions: {e.response_data}[/red]")
        raise typer.Exit(1)

    questions = data.get("questions", [])
    if not questions:
        console.print("[yellow]No questions found.[/yellow]")
        raise typer.Exit()

    # Group by category
    categories = {}
    for q in questions:
        cat = q.get("categoryId", "other")
        if cat not in categories:
            categories[cat] = {"title": q.get("categoryTitle", cat.upper()), "qs": []}
        categories[cat]["qs"].append(q)

    for cat_id, cat_data in categories.items():
        table = Table(
            show_header=True,
            header_style="bold cyan",
            box=box.ROUNDED,
            title=f"[bold white]{cat_data['title']}[/bold white]",
            title_style="bold",
            title_justify="left"
        )
        table.add_column("Status", width=18)
        table.add_column("ID", style="cyan", width=10)
        table.add_column("Title")
        table.add_column("Level", width=12)

        for q in cat_data["qs"]:
            if q.get("passed"):
                status_icon = "[bold green]\\[x] Passed[/bold green]"
            elif q.get("status") == "active":
                status_icon = "[bold yellow]\\[>] Active[/bold yellow]"
            else:
                status_icon = "[dim]\\[ ] Unattempted[/dim]"
            
            table.add_row(
                status_icon,
                q.get("id"),
                q.get("title"),
                q.get("level", "").capitalize()
            )
        console.print(table)
        console.print()


@app.command()
def start(
    question_id: str = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """
    Start a practice question environment.
    """
    utils.require_auth()
    
    if not question_id:
        # Interactive selection
        list_questions()
        console.print()
        question_id = Prompt.ask("[bold]Enter the ID of the question you want to start[/bold]")
        if not question_id:
            raise typer.Exit()

    question_id = utils.normalize_question_id(question_id)

    if not utils.check_prerequisites():
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting question [white]{question_id}[/white]...[/bold cyan]")
    cluster_name = f"aicademy-{question_id}"

    # Start the session via API
    try:
        data = api.start_session(question_id, cluster_name)
    except api.APIError as e:
        if e.status_code == 409:
            import json
            err_data = e.response_data
            if isinstance(err_data, str):
                try:
                    err_data = json.loads(err_data)
                except Exception:
                    pass

            if isinstance(err_data, dict) and "message" in err_data:
                try:
                    inner_data = json.loads(err_data["message"])
                    if isinstance(inner_data, dict):
                        err_data = inner_data
                except Exception:
                    pass
            
            if isinstance(err_data, dict) and err_data.get("code") == "SESSION_ACTIVE":
                active_qid = err_data.get("activeQuestionId", "unknown")
                active_sid = err_data.get("activeSessionId")
                
                console.print(f"\n[yellow]X You already have an active session for question [bold]{active_qid}[/bold].[/yellow]")
                if typer.confirm(f"Would you like to clear '{active_qid}' and start '{question_id}' instead?"):
                    kind.delete_cluster(f"aicademy-{active_qid}", verbose=verbose)
                    if active_sid:
                        try:
                            api.abandon_session(active_sid)
                        except api.APIError as e:
                            console.print(f"[dim yellow]⚠ Could not sync abandoned session to server: {e.response_data}[/dim yellow]")
                    config.set_active_session(None)
                    
                    console.print(f"\n[bold cyan]Retrying: Starting question [white]{question_id}[/white]...[/bold cyan]")
                    data = api.start_session(question_id, cluster_name)
                else:
                    raise typer.Exit()
            else:
                utils.format_access_error(e)
                raise typer.Exit(1)
        elif e.status_code == 402:
            utils.format_access_error(e)
            raise typer.Exit(1)
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
    kind.create_cluster(cluster_name, verbose=verbose)

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
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
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
    kind.delete_cluster(cluster_name, verbose=verbose)

    # Mark session as abandoned via API
    if session_id:
        try:
            api.abandon_session(session_id)
        except api.APIError as e:
            console.print(f"[dim yellow]⚠ Could not sync abandoned session to server: {e.response_data}[/dim yellow]")

    config.set_active_session(None)
    console.print(
        Panel(
            "[bold green]✓ Environment cleaned up.[/bold green]\n\n"
            "You can now start a new question with:\n"
            "[bold]aicademy question start <question-id>[/bold]",
            border_style="green",
        )
    )
