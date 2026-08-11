"""Verify command - runs declarative checks and reports results to the API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import typer
from rich.console import Console
from rich.prompt import Prompt

from .. import api, config
from ..core import utils
from ..core.ui import print_block
from ..core.utils import escape_rich_markup

# `core.verify_engine` transitively imports the `kubernetes` SDK — deferred
# to `_app_verify_async` so `--help`/`login`/`whoami`/etc. stay fast.


def _sign_verification_result(
    secret: str,
    session_id: str,
    question_id: str,
    passed: bool,
    score: int | None,
    check_results: list[dict[str, Any]],
) -> str:
    payload: dict[str, Any] = {
        "sessionId": session_id,
        "questionId": question_id,
        "passed": passed,
        "checkResults": check_results,
    }
    if score is not None:
        payload["score"] = score

    # ensure_ascii=False: the server's canonicalizer uses JS JSON.stringify
    # semantics, which keeps non-ASCII characters literal rather than
    # \uXXXX-escaping them. Signatures diverge on the default otherwise.
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

console = Console()


def app_verify(
    question_id: str | None = typer.Argument(
        None, help="Question ID (auto-detected from active session)"
    ),
) -> None:
    """Verify your solution for the current practice question."""
    asyncio.run(_app_verify_async(question_id))


async def _app_verify_async(question_id: str | None) -> None:
    from ..core import verify_engine  # deferred import — see module docstring
    from .question import _get_active_session_or_expire  # deferred — avoids a circular import

    utils.require_auth()

    session = await _get_active_session_or_expire()
    if not session and not question_id:
        console.print(
            "[red]✗ No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    session_id = (session or {}).get("sessionId")
    qid = question_id or (session or {}).get("questionId")
    cat = (session or {}).get("category", qid.split("-")[0] if qid else "")

    if not qid:
        console.print("[red]✗ Could not determine question ID.[/red]")
        raise typer.Exit(1)

    active_session = session or {}

    console.print(f"[bold cyan]Verifying question:[/bold cyan] [white]{qid}[/white]\n")

    try:
        qdata = await api.get_question(cat, qid)
        verify_checks = qdata.verifyChecks
    except Exception as e:
        console.print(f"[yellow]⚠ Could not fetch verification data from API: {e}[/yellow]")
        verify_checks = None

    if not verify_checks:
        console.print("[red]✗ No verification checks found for this question via API.[/red]")
        raise typer.Exit(1)

    console.print("[dim]Running declarative verification engine...[/dim]\n")
    cluster_name = active_session.get("clusterName")
    check_results = verify_engine.run_checks(
        [c.model_dump() for c in verify_checks], cluster_name=cluster_name
    )
    all_passed = all(r["passed"] for r in check_results)
    passed_count = sum(1 for r in check_results if r["passed"])
    total_count = len(check_results)

    console.print(f"[bold]Verification Results ({passed_count}/{total_count} passed):[/bold]")
    for r in check_results:
        icon = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
        color = "green" if r["passed"] else "red"
        name = escape_rich_markup(r["name"])
        console.print(f"  {icon} [{color}]{name}[/{color}]")
        if not r["passed"] and r["message"]:
            console.print(f"      [dim yellow]↳ {escape_rich_markup(r['message'])}[/dim yellow]")
    console.print()

    message = (
        f"All requirements met ({total_count}/{total_count}). Great work!"
        if all_passed
        else (
            f"Keep troubleshooting. {passed_count}/{total_count} tasks passed. "
            "Review the checklist above."
        )
    )
    result: dict[str, Any] = {"passed": all_passed, "message": message}

    if all_passed:
        print_block(
            console,
            "✓ Solution Verified",
            f"{result['message']}\n\nGreat work!",
            style="green",
        )
    else:
        print_block(
            console,
            "✗ Verify Failed",
            f"{result['message']}\n\n"
            "Keep troubleshooting. Run [bold]aicademy question instructions[/bold] "
            "to review tasks.",
            style="red",
        )

    # Report result to API, whether passed or failed
    if session_id:
        try:
            verification_secret = active_session.get("verificationSecret")
            if not verification_secret:
                console.print(
                    "[yellow]⚠ Session was started with an older CLI version. "
                    "Please clear and restart the question to enable result signing.[/yellow]"
                )
                raise typer.Exit(1)

            signature = _sign_verification_result(
                verification_secret,
                session_id,
                qid,
                all_passed,
                result.get("score"),
                check_results,
            )
            await api.verify_session(
                session_id,
                active_session.get("verificationToken", ""),
                check_results,
                result,
                signature,
            )
        except api.APIError as e:
            console.print(
                "[yellow]⚠ Could not sync verification result to server: "
                f"{e.response_data}[/yellow]"
            )

    if not all_passed:
        # Failed: results are already printed above. Nothing further to do --
        # no prompts, no side effects. The user fixes their solution and reruns.
        raise typer.Exit(1)

    next_step = _prompt_next_step()
    if next_step == "clear":
        from .question import _clear_async

        await _clear_async(question_id=question_id, verbose=False)
    elif next_step == "next":
        await _start_next_question(qid, active_session)
    else:
        console.print(
            "\n[dim]You can clean it up later with: [bold]aicademy question clear[/bold][/dim]"
        )


def _prompt_next_step() -> str:
    """Ask what to do after a pass: (c)lear & exit, (n)ext question, or
    (x)/anything else = exit. No validation loop -- an unrecognized answer
    is treated as "exit", not re-prompted, per the intended one-key flow."""
    console.print()
    raw = Prompt.ask(
        "[bold]What next?[/bold]  [green]\\[c][/green]lear & exit   "
        "[cyan]\\[n][/cyan]ext question   [dim]\\[x][/dim]it",
        default="x",
    )
    choice = raw.strip().lower()
    if choice.startswith("c"):
        return "clear"
    if choice.startswith("n"):
        return "next"
    return "exit"


async def _start_next_question(current_qid: str, active_session: dict[str, Any]) -> None:
    """(n)ext-question flow: fetch the next question this user can actually
    access and launch it directly, or explain why there isn't one --
    distinguishing "upgrade to see more" from "you're genuinely done"."""
    from .question import _start_async, _teardown_cluster

    try:
        next_data = await api.get_next_question(current_qid)
    except api.APIError as e:
        console.print(f"[red]✗ Could not fetch the next question: {e.response_data}[/red]")
        return

    next_question = next_data.get("nextQuestion")
    if next_question:
        # Tear down the just-finished question's cluster first -- otherwise
        # it's left running while a second one is created for the next
        # question. Only the exact cluster/session recorded for the current
        # question is deleted, never a wildcard.
        cluster_name = active_session.get("clusterName")
        if cluster_name:
            console.print(f"[dim]Cleaning up previous environment ({cluster_name})...[/dim]")
            await _teardown_cluster(cluster_name, active_session.get("sessionId"))
            config.set_active_session(None)

        next_id = next_question.get("id", "")
        console.print(
            f"\n[bold cyan]Next up:[/bold cyan] {escape_rich_markup(next_id)} — "
            f"{escape_rich_markup(next_question.get('title', ''))}\n"
        )
        await _start_async(next_id, verbose=False)
        return

    message = escape_rich_markup(str(next_data.get("message", "")))
    if next_data.get("code") == "UPGRADE_REQUIRED":
        upgrade_url = escape_rich_markup(
            str(next_data.get("upgradeUrl", "https://aicademy.ac/pricing"))
        )
        print_block(
            console,
            "💳 Upgrade Required",
            f"{message}\n\n[bold cyan]Upgrade at:[/bold cyan] {upgrade_url}",
            style="yellow",
        )
    else:
        print_block(console, "🎉 All Done", message, style="green")
