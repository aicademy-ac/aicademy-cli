from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from .. import api as api_client
from .. import config
from ..core import verify_engine

console = Console()


def get_log_path() -> Path:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return config.CONFIG_DIR / "kind.log"


def create_cluster(
    cluster_name: str,
    config_content: str | None = None,
    verbose: bool = False,
) -> None:
    console.print(f"\n[bold]Creating KIND cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    console.print("[dim]This may take 30-90 seconds...[/dim]\n")

    kind_cmd = ["kind", "create", "cluster", "--name", cluster_name]

    temp_config_path = None
    if config_content:
        fd, temp_config_path = tempfile.mkstemp(suffix=".yaml")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(config_content)
        kind_cmd.extend(["--config", temp_config_path])

    log_file = get_log_path()
    try:
        if verbose:
            subprocess.run(kind_cmd, check=True)
        else:
            with open(log_file, "w", encoding="utf-8") as f:
                subprocess.run(kind_cmd, check=True, stdout=f, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        console.print("[red]Failed to create KIND cluster.[/red]")
        console.print("[dim]Make sure Docker is running.[/dim]")
        if not verbose:
            console.print(f"[dim]Check logs for details: {log_file}[/dim]")
        raise typer.Exit(1) from None
    finally:
        if temp_config_path and os.path.exists(temp_config_path):
            os.remove(temp_config_path)

    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "kind",
                "export",
                "kubeconfig",
                "--name",
                cluster_name,
                "--kubeconfig",
                str(config.KUBECONFIG_PATH),
            ],
            check=True,
            stdout=subprocess.DEVNULL if not verbose else None,
            stderr=subprocess.STDOUT if not verbose else None,
        )
    except subprocess.CalledProcessError:
        console.print(
            "[yellow]Could not export kubeconfig; "
            "kubectl may fall back to the default config.[/yellow]"
        )


def delete_cluster(cluster_name: str, verbose: bool = False) -> None:
    console.print(f"[bold]Deleting cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    log_file = get_log_path()
    try:
        if verbose:
            subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=True)
        else:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- Deleting cluster {cluster_name} ---\n")
                subprocess.run(
                    ["kind", "delete", "cluster", "--name", cluster_name],
                    check=True,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                )
        console.print("[green]Cluster deleted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]Could not delete cluster (may not exist).[/yellow]")


async def verify_session(session: dict[str, Any], question_id: str) -> str:
    """Run verification checks for the active session and report the result."""
    category = question_id.split("-")[0]
    try:
        question = await api_client.get_question(category, question_id)
    except api_client.APIError as e:
        return f"Could not load question details: {e}"

    checks = question.get("verifyChecks") or question.get("verify_checks") or []
    if not checks:
        return "No verification checks defined for this question."

    results = verify_engine.run_checks(checks)
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    lines = [f"Verification: {passed}/{total} passed\n"]
    for r in results:
        icon = "OK" if r.get("passed") else "FAIL"
        color = "green" if r.get("passed") else "red"
        lines.append(f"[{color}]{icon}[/{color}] {r.get('name', 'Check')}")
        if not r.get("passed") and r.get("message"):
            lines.append(f"  [dim]{r['message']}[/dim]")
    return "\n".join(lines)
