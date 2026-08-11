"""Practice question commands — start, instructions, clear"""

from __future__ import annotations

import asyncio
import json
import webbrowser
from typing import Any
from urllib.parse import quote

import typer
from rich import box
from rich.console import Console
from rich.table import Table

from .. import api, config, state
from ..core import utils
from ..core.prefix_group import PrefixMatchingGroup
from ..core.ui import print_block
from ..core.utils import escape_rich_markup
from ..models import PracticeQuestion, StartSessionResponse
from .verify import app_verify

# `core.kind` / `core.cluster_setup` transitively import the `docker` and
# `kubernetes` SDKs, which are each a few hundred ms to import. `rich.markdown`
# pulls in `markdown-it` similarly. Deferring these to the functions that
# actually need them keeps `--help`, `login`, `whoami`, `list`, etc. fast —
# they never pay that cost.

console = Console()
app = typer.Typer(help="Manage practice question sessions", cls=PrefixMatchingGroup)

# Local display names -- the server's question-list items carry only the
# short `category` slug (cka/ckad/cks), never a title. Bounded, unlikely to
# change; avoids a round trip just to render a table heading.
_CATEGORY_TITLES: dict[str, str] = {
    "cka": "CKA — Certified Kubernetes Administrator",
    "ckad": "CKAD — Certified Kubernetes Application Developer",
    "cks": "CKS — Certified Kubernetes Security Specialist",
}

# Shared across list/start/launch -- OptionInfo objects are plain metadata
# read at decoration time, safe to reuse as the default for the same named
# flag on multiple commands (keeps help text identical everywhere for free).
_CKA_OPT = typer.Option(False, "--cka", help="Only CKA questions")
_CKAD_OPT = typer.Option(False, "--ckad", help="Only CKAD questions")
_CKS_OPT = typer.Option(False, "--cks", help="Only CKS questions")
_BEGINNER_OPT = typer.Option(False, "--beginner", help="Only beginner-level questions")
_INTERMEDIATE_OPT = typer.Option(False, "--intermediate", help="Only intermediate-level questions")
_ADVANCED_OPT = typer.Option(False, "--advanced", help="Only advanced-level questions")
_EXPERT_OPT = typer.Option(False, "--expert", help="Only expert-level questions")


def _resolve_category_flag(cka: bool, ckad: bool, cks: bool) -> str | None:
    selected = [name for name, flag in (("cka", cka), ("ckad", ckad), ("cks", cks)) if flag]
    if len(selected) > 1:
        flags = ", ".join(f"--{s}" for s in selected)
        console.print(f"[red]✗ Choose only one category flag, not {flags}.[/red]")
        raise typer.Exit(1)
    return selected[0] if selected else None


def _resolve_level_flag(
    beginner: bool, intermediate: bool, advanced: bool, expert: bool
) -> str | None:
    selected = [
        name
        for name, flag in (
            ("beginner", beginner),
            ("intermediate", intermediate),
            ("advanced", advanced),
            ("expert", expert),
        )
        if flag
    ]
    if len(selected) > 1:
        flags = ", ".join(f"--{s}" for s in selected)
        console.print(f"[red]✗ Choose only one level flag, not {flags}.[/red]")
        raise typer.Exit(1)
    return selected[0] if selected else None


@app.command("list")
def list_questions(
    cka: bool = _CKA_OPT,
    ckad: bool = _CKAD_OPT,
    cks: bool = _CKS_OPT,
    beginner: bool = _BEGINNER_OPT,
    intermediate: bool = _INTERMEDIATE_OPT,
    advanced: bool = _ADVANCED_OPT,
    expert: bool = _EXPERT_OPT,
) -> None:
    """List available questions and your progress. Filter with --cka/--ckad/--cks
    and --beginner/--intermediate/--advanced/--expert."""
    category = _resolve_category_flag(cka, ckad, cks)
    level = _resolve_level_flag(beginner, intermediate, advanced, expert)
    asyncio.run(_list_questions_async(category, level))


async def _list_questions_async(category: str | None = None, level: str | None = None) -> None:
    utils.require_auth()
    try:
        questions = await api.get_all_questions()
    except api.APIError as e:
        console.print(f"[red]✗ Failed to load questions: {e.response_data}[/red]")
        raise typer.Exit(1) from e

    if category:
        questions = [q for q in questions if q.get("category") == category]
    if level:
        questions = [q for q in questions if q.get("level") == level]

    if not questions:
        message = (
            "[yellow]No questions match that filter.[/yellow]"
            if (category or level)
            else "[yellow]No questions found.[/yellow]"
        )
        console.print(message)
        raise typer.Exit()

    try:
        progress = await api.get_progress()
    except api.APIError as e:
        console.print(f"[dim yellow]⚠ Could not load progress: {e.response_data}[/dim yellow]")
        progress = {}

    # Group by category. Questions arrive pre-grouped by category (cka, then
    # ckad, then cks), so a plain dict preserves that display order for free.
    categories: dict[str, dict[str, Any]] = {}
    for q in questions:
        cat = q.get("category", "other")
        if cat not in categories:
            categories[cat] = {"title": _CATEGORY_TITLES.get(cat, cat.upper()), "qs": []}
        categories[cat]["qs"].append(q)

    for cat_data in categories.values():
        table = Table(
            show_header=True,
            header_style="bold cyan",
            box=box.SIMPLE_HEAVY,
            title=f"[bold white]{cat_data['title']}[/bold white]",
            title_style="bold",
            title_justify="left",
        )
        table.add_column("Status", width=14)
        table.add_column("ID", style="cyan", width=9)
        table.add_column("Title")
        table.add_column("Level", width=12)

        for q in cat_data["qs"]:
            qid = q.get("id", "")
            entry = progress.get(qid, {})
            if entry.get("passed"):
                status_icon = "[bold green]✓ Passed[/bold green]"
            elif entry.get("status") == "active":
                status_icon = "[bold yellow]▸ Active[/bold yellow]"
            else:
                status_icon = "[dim]· Unattempted[/dim]"

            table.add_row(
                status_icon,
                qid,
                escape_rich_markup(q.get("title", "")),
                q.get("level", "").capitalize(),
            )
        console.print(table)
        console.print()


@app.command()
def start(
    question_id: str | None = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
    cka: bool = _CKA_OPT,
    ckad: bool = _CKAD_OPT,
    cks: bool = _CKS_OPT,
    beginner: bool = _BEGINNER_OPT,
    intermediate: bool = _INTERMEDIATE_OPT,
    advanced: bool = _ADVANCED_OPT,
    expert: bool = _EXPERT_OPT,
) -> None:
    """Start a practice question environment. With no ID, browse questions
    interactively -- narrow with --cka/--ckad/--cks and level flags first."""
    category = _resolve_category_flag(cka, ckad, cks)
    level = _resolve_level_flag(beginner, intermediate, advanced, expert)
    asyncio.run(_start_async(question_id, verbose, category, level))


@app.command()
def launch(
    question_id: str | None = typer.Argument(None, help="Question ID to start, e.g. cka-01"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show full command output"),
    cka: bool = _CKA_OPT,
    ckad: bool = _CKAD_OPT,
    cks: bool = _CKS_OPT,
    beginner: bool = _BEGINNER_OPT,
    intermediate: bool = _INTERMEDIATE_OPT,
    advanced: bool = _ADVANCED_OPT,
    expert: bool = _EXPERT_OPT,
) -> None:
    """Alias for `aicademy question start`."""
    category = _resolve_category_flag(cka, ckad, cks)
    level = _resolve_level_flag(beginner, intermediate, advanced, expert)
    asyncio.run(_start_async(question_id, verbose, category, level))


async def _pick_question_interactively(category: str | None, level: str | None) -> str | None:
    """No question ID given: browse and pick one. A --cka/--ckad/--cks flag
    skips the category prompt; otherwise ask interactively. Returns None if
    nothing matched the filter or the user cancelled (Ctrl+C/Esc) --
    callers should treat that as a clean exit, not an error."""
    from ..core import question_browser

    try:
        questions = await api.get_all_questions()
    except api.APIError as e:
        console.print(f"[red]✗ Failed to load questions: {e.response_data}[/red]")
        raise typer.Exit(1) from e

    if category is None:
        console.print()
        category = question_browser.pick_category()

    if category:
        questions = [q for q in questions if q.get("category") == category]
    if level:
        questions = [q for q in questions if q.get("level") == level]

    if not questions:
        console.print("[yellow]No questions match that filter.[/yellow]")
        return None

    try:
        progress = await api.get_progress()
    except api.APIError:
        progress = {}

    return question_browser.pick_question(questions, progress)


async def _start_async(
    question_id: str | None,
    verbose: bool,
    category: str | None = None,
    level: str | None = None,
) -> None:
    from ..core import cluster_setup, kind  # deferred import — see module docstring

    if verbose:
        state.set_verbose(True)
    utils.require_auth()

    if not question_id:
        question_id = await _pick_question_interactively(category, level)
        if not question_id:
            raise typer.Exit()

    qid = utils.normalize_question_id(question_id)
    if not qid:
        console.print("[red]✗ Invalid question ID.[/red]")
        raise typer.Exit(1)

    if not utils.check_prerequisites():
        raise typer.Exit(1)

    console.print(f"\n[bold cyan]Starting question [white]{qid}[/white]...[/bold cyan]")
    cluster_name = f"aicademy-{qid}"

    data: StartSessionResponse | None = None
    try:
        data = await api.start_session(qid, cluster_name)
    except api.APIError as e:
        data = await _handle_start_conflict(qid, cluster_name, e, verbose)
        if data is None:
            raise typer.Exit(1) from None

    if data is None:
        raise typer.Exit(1) from None

    question = data.question

    # Cache session locally
    config.set_active_session(
        {
            "sessionId": data.sessionId,
            "questionId": qid,
            "clusterName": cluster_name,
            "category": question.category,
            "verificationToken": data.verificationToken,
            "verificationSecret": data.verificationSecret,
        }
    )

    # Create KIND cluster
    kind.create_cluster(
        cluster_name,
        config_content=data.kindConfigContent,
        verbose=verbose,
    )

    # Apply declarative cluster state if provided
    if data.clusterState:
        try:
            await cluster_setup.apply_cluster_state(
                cluster_name,
                data.clusterState.model_dump(),
                config.KUBECONFIG_PATH,
                cluster_template=question.clusterTemplate,
            )
        except cluster_setup.ClusterSetupError as e:
            console.print(f"[red]✗ Cluster setup failed: {e}[/red]")
            console.print(
                "[dim]The cluster was created but may be partially configured. "
                f"Run [bold]aicademy question clear {qid}[/bold] to clean up and try again.[/dim]"
            )
            raise typer.Exit(1) from e

    # Apply declarative breakers (chaos/failure injection) if provided
    if data.breakers:
        try:
            await cluster_setup.apply_breakers(
                cluster_name,
                [b.model_dump() for b in data.breakers],
                config.KUBECONFIG_PATH,
                cluster_template=question.clusterTemplate,
            )
        except cluster_setup.ClusterSetupError as e:
            console.print(f"[red]✗ Breaker injection failed: {e}[/red]")
            console.print(
                "[dim]The cluster is otherwise ready. "
                f"Run [bold]aicademy question clear {qid}[/bold] to clean up and try again.[/dim]"
            )
            raise typer.Exit(1) from e

    # Reveal: clear the noise from cluster setup, show a one-line "ready"
    # header, then the full instructions immediately -- no separate
    # `aicademy instructions` step required to see what to do. Skipped in
    # --verbose mode, which implies "show me everything, don't hide it".
    if not verbose:
        console.clear()
    console.print(
        f"[bold green]✓ Lab ready:[/bold green] [white]{qid}[/white] — "
        f"{escape_rich_markup(question.title)}  [dim]({cluster_name})[/dim]\n"
    )
    _print_question_instructions(qid, question)


async def _handle_start_conflict(
    qid: str,
    cluster_name: str,
    e: api.APIError,
    verbose: bool,
) -> StartSessionResponse | None:
    from ..core import kind  # deferred import — see module docstring

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
        if typer.confirm(
            f"Would you like to clear '{active_qid}' and start '{qid}' instead?", default=True
        ):
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


def _print_question_instructions(qid: str, q: PracticeQuestion) -> None:
    """Render a question's full scenario/tasks/hints to the terminal.

    Shared by `aicademy question instructions` and the post-`start` reveal
    so the two never drift out of sync with each other.
    """
    from rich.markdown import Markdown
    from rich.padding import Padding

    print_block(
        console,
        f"📋 Question {qid}",
        f"[bold]{escape_rich_markup(q.title)}[/bold]\n\n"
        f"[dim]Category:[/dim] {escape_rich_markup(q.category.upper())}  "
        f"[dim]Level:[/dim] {escape_rich_markup(q.level.capitalize())}  "
        f"[dim]Time:[/dim] ~{q.estimatedMinutes}m",
        style="cyan",
    )

    if q.scenario:
        console.print("\n[bold cyan]Scenario[/bold cyan]")
        console.print("[cyan]" + "─" * min(max(len("Scenario"), 20), 60) + "[/cyan]")
        console.print(Markdown(escape_rich_markup(q.scenario)))

    if q.tasks:
        console.print("\n[bold cyan]Tasks[/bold cyan]")
        console.print("[cyan]" + "─" * min(max(len("Tasks"), 20), 60) + "[/cyan]")
        for i, task in enumerate(q.tasks, 1):
            console.print(f"\n[bold]{i}. {escape_rich_markup(task.title)}[/bold]")
            console.print(Padding(escape_rich_markup(task.description), (0, 0, 0, 3)))

    if q.hints:
        console.print("\n[bold dim]Hints (expand if stuck)[/bold dim]")
        for hint in q.hints:
            console.print(f"  [dim]→ {escape_rich_markup(hint)}[/dim]")

    console.print("\n[dim]When done:[/dim]   [bold]aicademy verify[/bold]")
    console.print("[dim]To clean up:[/dim] [bold]aicademy question clear[/bold]")


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
        if not utils.is_valid_category(cat):
            cat = qid.split("-")[0] if qid else ""
        url = f"{config.API_BASE_URL}/practice/{quote(cat, safe='')}/{quote(qid, safe='')}"
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

    _print_question_instructions(qid, data.question)


@app.command("break")
def break_env(
    question_id: str | None = typer.Argument(
        None, help="Question ID (auto-detected from active session)"
    ),
) -> None:
    """Re-apply breakers (chaos/failure injection) to the current practice environment."""
    asyncio.run(_break_async(question_id))


async def _break_async(question_id: str | None) -> None:
    from ..core import cluster_setup  # deferred import — see module docstring

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

    cat = (session or {}).get("category", qid.split("-")[0] if qid else "")

    try:
        data = await api.get_question(cat, qid)
    except api.APIError as e:
        console.print(f"[red]✗ API error ({e.status_code}): {e.response_data}[/red]")
        raise typer.Exit(1) from e

    breakers = data.question.breakers
    if not breakers:
        console.print("[yellow]This question has no breakers configured.[/yellow]")
        return

    cluster_name = (session or {}).get("clusterName") or f"aicademy-{qid}"
    if not utils.is_valid_cluster_name(cluster_name):
        console.print("[red]✗ Invalid cluster name.[/red]")
        raise typer.Exit(1)
    console.print(
        f"[bold cyan]Re-applying breakers to [white]{cluster_name}[/white]...[/bold cyan]"
    )

    try:
        await cluster_setup.apply_breakers(
            cluster_name,
            [b.model_dump() for b in breakers],
            config.KUBECONFIG_PATH,
            cluster_template=data.question.clusterTemplate,
        )
        console.print("[bold green]✓ Breakers applied successfully.[/bold green]")
    except cluster_setup.ClusterSetupError as e:
        console.print(f"[red]✗ Breaker injection failed: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def verify(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """Verify your solution for the current practice question."""
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
    from ..core import kind  # deferred import — see module docstring

    if verbose:
        state.set_verbose(True)
    utils.require_auth()

    qid = utils.normalize_question_id(question_id)
    session = config.get_active_session()
    if not session and not qid:
        console.print("[yellow]No active session found.[/yellow]")
        raise typer.Exit()

    session_id = (session or {}).get("sessionId")
    cluster_name = (session or {}).get("clusterName") or f"aicademy-{qid}"
    if not utils.is_valid_cluster_name(cluster_name):
        console.print("[red]✗ Invalid cluster name.[/red]")
        raise typer.Exit(1)

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
    print_block(
        console,
        "✓ Environment cleaned up.",
        "You can now start a new question with:\n[bold]aicademy start <question-id>[/bold]",
        style="green",
    )
