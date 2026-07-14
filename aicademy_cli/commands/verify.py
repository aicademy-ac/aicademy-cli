"""Verify command - runs declarative checks and reports results to the API."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from .. import api, config
from ..core import utils, verify_engine
from ..core.utils import escape_rich_markup


def _sign_verification_result(
    secret: str,
    session_id: str,
    question_id: str,
    passed: bool,
    score: int | None,
    check_results: list[dict[str, Any]],
) -> str:
    """Compute an HMAC-SHA256 signature over the verification result payload."""
    canonical = json.dumps(
        {
            "sessionId": session_id,
            "questionId": question_id,
            "passed": passed,
            "score": score,
            "checkResults": check_results,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

console = Console()


def app_verify(
    question_id: str | None = typer.Argument(
        None, help="Question ID (auto-detected from active session)"
    ),
) -> None:
    """
    Verify your solution for the current practice question.
    """
    asyncio.run(_app_verify_async(question_id))


async def _app_verify_async(question_id: str | None) -> None:
    utils.require_auth()

    session = config.get_active_session()
    if not session and not question_id:
        console.print(
            "[red]X No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    session_id = (session or {}).get("sessionId")
    qid = question_id or (session or {}).get("questionId")
    cat = (session or {}).get("category", qid.split("-")[0] if qid else "")

    if not qid:
        console.print("[red]X Could not determine question ID.[/red]")
        raise typer.Exit(1)

    active_session = session or {}

    console.print(f"[bold cyan]Verifying question:[/bold cyan] [white]{qid}[/white]\n")

    try:
        qdata = await api.get_question(cat, qid)
        verify_checks = qdata.verifyChecks
    except Exception as e:
        console.print(f"[yellow]! Could not fetch verification data from API: {e}[/yellow]")
        verify_checks = None

    if not verify_checks:
        console.print("[red]X No verification checks found for this question via API.[/red]")
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
        console.print(
            Panel(
                f"[bold green]OK PASSED![/bold green]\n\n{result['message']}\n\nGreat work!",
                title="Solution Verified",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]X Not yet passing[/bold red]\n\n{result['message']}\n\n"
                "Keep troubleshooting. Run [bold]aicademy question instructions[/bold] "
                "to review tasks.",
                title="Verify Failed",
                border_style="red",
            )
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

    if all_passed:
        if typer.confirm("\nWould you like to clear the practice environment now?"):
            from .question import _clear_async

            await _clear_async(question_id=question_id, verbose=False)
        else:
            console.print(
                "\n[dim]You can clean it up later with: [bold]aicademy question clear[/bold][/dim]"
            )
    else:
        raise typer.Exit(1)
