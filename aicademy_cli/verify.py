"""Verify command — runs the local verify.sh and reports results to the API"""

import subprocess
import json
from pathlib import Path
import typer
import httpx
from rich.console import Console
from rich.panel import Panel
from . import config

console = Console()


def app_verify(
    question_id: str = typer.Argument(None, help="Question ID (auto-detected from active session)"),
) -> None:
    """
    Verify your solution for the current practice question.

    Runs the local verify.sh script inside the KIND cluster and reports
    the result to Aicademy. Requires an active session.
    """
    token = config.get_token()
    if not token:
        console.print("[red]✗ Not logged in.[/red] Run [bold]aicademy login[/bold] first.")
        raise typer.Exit(1)

    session = config.get_active_session()
    if not session and not question_id:
        console.print(
            "[red]✗ No active session.[/red] Run [bold]aicademy question start <id>[/bold] first."
        )
        raise typer.Exit(1)

    session_id = (session or {}).get("sessionId")
    qid = question_id or (session or {}).get("questionId")
    cat = (session or {}).get("category", qid.split("-")[0] if qid else "")

    console.print(f"[bold cyan]Verifying question:[/bold cyan] [white]{qid}[/white]\n")

    # Locate verify script — it ships with the CLI data bundle
    # In local dev, look relative to the aicademy-cli repo
    script_candidates = [
        Path(__file__).parent.parent / "questions" / cat / qid / "verify.sh",
        Path.cwd() / "verify.sh",
    ]

    verify_script = None
    for candidate in script_candidates:
        if candidate.exists():
            verify_script = candidate
            break

    if not verify_script:
        console.print(
            "[yellow]⚠ verify.sh not found locally.[/yellow]\n"
            "Reporting a manual verification — please confirm your solution is correct."
        )
        passed = typer.confirm("Did your solution pass?", default=True)
        result = {"passed": passed, "message": "Manual verification by user."}
    else:
        console.print(f"[dim]Running:[/dim] {verify_script}\n")
        try:
            proc = subprocess.run(
                ["bash", str(verify_script)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            passed = proc.returncode == 0
            message = proc.stdout.strip() or proc.stderr.strip() or "Verify script completed."
            result = {"passed": passed, "message": message}
        except subprocess.TimeoutExpired:
            console.print("[red]✗ Verify script timed out (120s).[/red]")
            raise typer.Exit(1)
        except FileNotFoundError:
            console.print("[red]✗ bash not found. Install Git Bash or WSL on Windows.[/red]")
            raise typer.Exit(1)

    # Display result
    if result["passed"]:
        console.print(
            Panel(
                f"[bold green]✓ PASSED![/bold green]\n\n{result['message']}\n\n"
                "Great work! Clean up with: [bold]aicademy question clear[/bold]",
                title="🎉  Solution Verified",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[bold red]✗ Not yet passing[/bold red]\n\n{result['message']}\n\n"
                "Keep troubleshooting. Run [bold]aicademy question instructions[/bold] to review tasks.",
                title="🔧  Verify Failed",
                border_style="red",
            )
        )

    # Report result to API
    if session_id:
        try:
            httpx.post(
                f"{config.API_BASE_URL}/api/practice/sessions/{session_id}/verify",
                json=result,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            if result["passed"]:
                config.set_active_session(None)
        except httpx.RequestError:
            pass  # Fail silently — local result is authoritative

    if not result["passed"]:
        raise typer.Exit(1)
