"""Verify command — runs the local verify.sh and reports results to the API"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel

from .. import api, config
from ..core import utils, verify_engine

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

    # Fetch verify script and checks from API
    verify_script_content: str | None = None
    verify_checks: list[dict[str, Any]] | None = None
    try:
        qdata = await api.get_question(cat, qid)
        verify_script_content = qdata.get("verifyScript")
        verify_checks = qdata.get("verifyChecks")
    except Exception as e:
        console.print(f"[yellow]! Could not fetch verification data from API: {e}[/yellow]")

    if not verify_script_content and not verify_checks:
        console.print("[red]X No verification logic found for this question via API.[/red]")
        raise typer.Exit(1)

    check_results: list[dict[str, Any]] | None = None
    if verify_checks:
        # Run new Python declarative engine
        console.print("[dim]Running declarative verification engine...[/dim]\n")

        check_results = verify_engine.run_checks(verify_checks)
        all_passed = all(r["passed"] for r in check_results)
        passed_count = sum(1 for r in check_results if r["passed"])
        total_count = len(check_results)

        console.print(f"[bold]Verification Results ({passed_count}/{total_count} passed):[/bold]")
        for r in check_results:
            icon = "[green]✓[/green]" if r["passed"] else "[red]✗[/red]"
            color = "green" if r["passed"] else "red"
            console.print(f"  {icon} [{color}]{r['name']}[/{color}]")
            if not r["passed"] and r["message"]:
                console.print(f"      [dim yellow]↳ {r['message']}[/dim yellow]")
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
    else:
        # Legacy bash execution
        if verify_script_content is None:
            console.print("[red]X No verify script content available.[/red]")
            raise typer.Exit(1)
        verify_script_content = verify_script_content.replace("\r", "")

        if sys.platform == "win32":
            verify_script_content = (
                """
if command -v kubectl.exe &> /dev/null; then
    kubectl() {
        kubectl.exe "$@" < /dev/null
    }
fi
"""
                + verify_script_content
            )

        console.print("[dim]Running verify script from API...[/dim]\n")
        try:
            proc = subprocess.run(
                ["bash"],
                input=verify_script_content.encode("utf-8"),
                capture_output=True,
                timeout=120,
            )
            passed = proc.returncode == 0
            message = (
                proc.stdout.decode("utf-8", errors="replace")
                + "\n"
                + proc.stderr.decode("utf-8", errors="replace")
            ).strip() or "Verify script completed."
            message = message.encode("cp1252", errors="replace").decode("cp1252")
            result = {"passed": passed, "message": message}
        except subprocess.TimeoutExpired:
            console.print("[red]⚠ Verification script timed out.[/red]")
            raise typer.Exit(1) from None
        except FileNotFoundError:
            console.print("[red]X bash not found. Install Git Bash or WSL on Windows.[/red]")
            raise typer.Exit(1) from None

    if result["passed"]:
        console.print(
            Panel(
                f"[bold green]OK PASSED![/bold green]\n\n{result['message']}\n\nGreat work!",
                title="Solution Verified",
                border_style="green",
            )
        )

        # Report result to API before prompting so it's saved immediately
        if session_id:
            try:
                await api.verify_session(
                    session_id,
                    active_session.get("verificationToken", ""),
                    check_results,
                    result,
                )
            except api.APIError as e:
                console.print(
                    "[yellow]⚠ Could not sync verification result to server: "
                    f"{e.response_data}[/yellow]"
                )

        if typer.confirm("\nWould you like to clear the practice environment now?"):
            from .question import clear

            clear(question_id=question_id, verbose=False)
        else:
            console.print(
                "\n[dim]You can clean it up later with: [bold]aicademy question clear[/bold][/dim]"
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

    # If not passed, we still need to report the failed attempt
    if not result["passed"]:
        if session_id:
            try:
                await api.verify_session(
                    session_id,
                    active_session.get("verificationToken", ""),
                    check_results,
                    result,
                )
            except api.APIError as e:
                console.print(
                    "[dim yellow]⚠ Could not sync failed attempt to server: "
                    f"{e.response_data}[/dim yellow]"
                )
        raise typer.Exit(1)
