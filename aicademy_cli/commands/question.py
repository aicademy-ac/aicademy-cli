"""Practice question commands — start, instructions, clear"""

from __future__ import annotations

import asyncio
import json
import subprocess
import webbrowser
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .. import api, config
from ..core import kind, utils
from .verify import app_verify

console = Console()
app = typer.Typer(help="Manage practice question sessions")


@app.command("list")
def list_questions() -> None:
    """List all available questions and your progress."""
    asyncio.run(_list_questions_async())


async def _list_questions_async() -> None:
    utils.require_auth()
    try:
        data = await api.get_all_questions()
    except api.APIError as e:
        console.print(f"[red]✗ Failed to load questions: {e.response_data}[/red]")
        raise typer.Exit(1) from e

    questions = data.get("questions", [])
    if not questions:
        console.print("[yellow]No questions found.[/yellow]")
        raise typer.Exit()

    # Group by category
    categories: dict[str, dict[str, Any]] = {}
    for q in questions:
        cat = q.get("categoryId", "other")
        if cat not in categories:
            categories[cat] = {"title": q.get("categoryTitle", cat.upper()), "qs": []}
        categories[cat]["qs"].append(q)

    for cat_data in categories.values():
        table = Table(
            show_header=True,
            header_style="bold cyan",
            box=box.ROUNDED,
            title=f"[bold white]{cat_data['title']}[/bold white]",
            title_style="bold",
            title_justify="left",
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
                q.get("level", "").capitalize(),
            )
        console.print(table)
        console.print()


@app.command()
def start(
    question_id: str | None = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """
    Start a practice question environment.
    """
    asyncio.run(_start_async(question_id, verbose))


@app.command()
def launch(
    question_id: str | None = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """Alias for `aicademy question start`."""
    start(question_id=question_id, verbose=verbose)


async def _start_async(question_id: str | None, verbose: bool) -> None:
    utils.require_auth()

    if not question_id:
        # Interactive selection
        await _list_questions_async()
        console.print()
        selected = Prompt.ask("[bold]Enter the ID of the question you want to start[/bold]")
        if not selected:
            raise typer.Exit()
        question_id = selected

    qid = utils.normalize_question_id(question_id)
    if not qid:
        console.print("[red]✗ Invalid question ID.[/red]")
        raise typer.Exit(1)

    if not utils.check_prerequisites():
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting question [white]{qid}[/white]...[/bold cyan]")
    cluster_name = f"aicademy-{qid}"

    data: dict[str, Any] | None = None
    try:
        data = await api.start_session(qid, cluster_name)
    except api.APIError as e:
        data = await _handle_start_conflict(qid, cluster_name, e, verbose)
        if data is None:
            raise typer.Exit(1) from None

    if data is None:
        raise typer.Exit(1) from None

    session = data
    question = data.get("question", {})

    # Cache session locally
    config.set_active_session(
        {
            "sessionId": session.get("sessionId"),
            "questionId": qid,
            "clusterName": cluster_name,
            "category": question.get("category", ""),
            "verificationToken": session.get("verificationToken"),
        }
    )

    # Create KIND cluster
    kind.create_cluster(
        cluster_name,
        config_content=data.get("kindConfigContent"),
        verbose=verbose,
    )

    # Run setup commands if any
    setup_commands = data.get("setupCommands", [])
    if setup_commands:
        console.print("\n[bold cyan]Running setup commands...[/bold cyan]")
        for cmd in setup_commands:
            console.print(f"[dim]Running: {cmd}[/dim]")
            try:
                subprocess.run(cmd, shell=True, check=True)
            except subprocess.CalledProcessError as e:
                console.print(f"[red]✗ Setup command failed: {e}[/red]")
                console.print(
                    "[dim yellow]Proceeding anyway, but the environment may not be "
                    "correctly prepared.[/dim yellow]"
                )

    # Print success panel
    md = Markdown(
        "- **aicademy question instructions** — read full tasks\n"
        "- **aicademy verify**                 — check your solution\n"
        "- **aicademy question clear**         — clean up when done"
    )
    console.print(
        Panel(
            f"[bold green]✓ Environment Ready![/bold green]\n\n"
            f"[bold]Question:[/bold]  {question.get('title', qid)}\n"
            f"[bold]Level:[/bold]     {question.get('level', '').capitalize()}\n"
            f"[bold]Category:[/bold]  {question.get('category', '').upper()}\n"
            f"[bold]Cluster:[/bold]   {cluster_name}\n"
            f"[bold]Time:[/bold]      ~{question.get('estimatedMinutes', '?')} minutes\n\n"
            "[bold]Next steps:[/bold]",
            title="🚀  Session Started",
            border_style="green",
        )
    )
    console.print(md)


async def _handle_start_conflict(
    qid: str,
    cluster_name: str,
    e: api.APIError,
    verbose: bool,
) -> dict[str, Any] | None:
    if e.status_code != 409:
        if e.status_code == 402:
            utils.format_access_error(e)
        else:
            console.print(f"[red]✗ API error ({e.status_code}): {e.response_data}[/red]")
        return None

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

        console.print(
            f"\n[yellow]X You already have an active session for question "
            f"[bold]{active_qid}[/bold].[/yellow]"
        )
        if typer.confirm(f"Would you like to clear '{active_qid}' and start '{qid}' instead?"):
            kind.delete_cluster(f"aicademy-{active_qid}", verbose=verbose)
            if active_sid:
                try:
                    await api.abandon_session(active_sid)
                except api.APIError as e2:
                    console.print(
                        "[dim yellow]⚠ Could not sync abandoned session to server: "
                        f"{e2.response_data}[/dim yellow]"
                    )
            config.set_active_session(None)

            console.print(
                f"\n[bold cyan]Retrying: Starting question [white]{qid}[/white]...[/bold cyan]"
            )
            try:
                return await api.start_session(qid, cluster_name)
            except api.APIError as e2:
                console.print(f"[red]✗ API error ({e2.status_code}): {e2.response_data}[/red]")
                return None
        else:
            raise typer.Exit()
    else:
        utils.format_access_error(e)
        return None


@app.command()
def instructions(
    question_id: str | None = typer.Argument(
        None, help="Question ID (auto-detected from active session)"
    ),
    web: bool = typer.Option(False, "--web", help="Open the question page in browser instead"),
) -> None:
    """Show full question instructions in the terminal."""
    asyncio.run(_instructions_async(question_id, web))


async def _instructions_async(question_id: str | None, web: bool) -> None:
    utils.require_auth()

    session = config.get_active_session()
    if not session and not question_id:
        console.print(
            "[red]✗ No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    qid = utils.normalize_question_id(question_id) or (
        session.get("questionId") if session else None
    )
    if not qid:
        console.print("[red]✗ Could not determine question ID.[/red]")
        raise typer.Exit(1)

    if web:
        cat = session.get("category", "") if session else ""
        url = f"{config.API_BASE_URL}/practice/{cat}/{qid}"
        console.print(f"[cyan]Opening:[/cyan] {url}")
        webbrowser.open(url)
        raise typer.Exit()

    session_data = config.get_active_session() or {}
    cat = session_data.get("category", qid.split("-")[0] if qid else "")

    try:
        data = await api.get_question(cat, qid)
    except api.APIError as e:
        if e.status_code == 403:
            console.print(
                "[red]✗ No active session found for this question.[/red]\n"
                f"Run: [bold]aicademy question start {qid}[/bold]"
            )
        else:
            console.print(f"[red]✗ {e.status_code}: {e.response_data}[/red]")
        raise typer.Exit(1) from e

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
        "\n[dim]When done:[/dim] [bold]aicademy verify[/bold]  |  "
        "[dim]To clean up:[/dim] [bold]aicademy question clear[/bold]"
    )


@app.command()
def verify(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """
    Verify your solution for the current practice question.
    """
    app_verify(question_id=question_id)


@app.command()
def clear(
    question_id: str | None = typer.Argument(
        None, help="Question ID (auto-detected from active session)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
) -> None:
    """Clean up the practice environment."""
    asyncio.run(_clear_async(question_id, verbose))


async def _clear_async(question_id: str | None, verbose: bool) -> None:
    utils.require_auth()

    qid = utils.normalize_question_id(question_id)
    session = config.get_active_session()
    if not session and not qid:
        console.print("[yellow]No active session found.[/yellow]")
        raise typer.Exit()

    session_id = (session or {}).get("sessionId")
    cluster_name = (session or {}).get("clusterName") or f"aicademy-{qid}"

    # Delete KIND cluster
    kind.delete_cluster(cluster_name, verbose=verbose)

    # Mark session as abandoned via API
    if session_id:
        try:
            await api.abandon_session(session_id)
        except api.APIError as e:
            console.print(
                "[dim yellow]⚠ Could not sync abandoned session to server: "
                f"{e.response_data}[/dim yellow]"
            )

    config.set_active_session(None)
    console.print(
        Panel(
            "[bold green]✓ Environment cleaned up.[/bold green]\n\n"
            "You can now start a new question with:\n"
            "[bold]aicademy start <question-id>[/bold]",
            border_style="green",
        )
    )
