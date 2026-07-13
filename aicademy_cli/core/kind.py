"""KIND cluster lifecycle helpers."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import typer
from rich.console import Console

from .. import config
from .cluster_context import ClusterTargetingError

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
        if sys.platform != "win32" and config.KUBECONFIG_PATH.exists():
            os.chmod(config.KUBECONFIG_PATH, 0o600)
    except subprocess.CalledProcessError as exc:
        console.print(
            "[red]Could not export kubeconfig for the practice cluster. "
            "Aborting to avoid targeting the default cluster.[/red]"
        )
        raise typer.Exit(1) from exc


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


def ensure_cluster_targeted(cluster_name: str) -> None:
    """Raise ClusterTargetingError if the active kubeconfig does not match cluster_name."""
    if not config.KUBECONFIG_PATH.exists():
        raise ClusterTargetingError(
            f"Practice kubeconfig not found: {config.KUBECONFIG_PATH}. "
            f"Start the question with 'aicademy question start {cluster_name}' first."
        )
    # Parse kubeconfig to confirm current context points at cluster_name
    import yaml

    try:
        data = yaml.safe_load(config.KUBECONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ClusterTargetingError(f"Could not parse kubeconfig: {exc}") from exc
    if not isinstance(data, dict):
        raise ClusterTargetingError("Invalid kubeconfig format.")
    current_ctx = data.get("current-context")
    contexts = {c.get("name"): c for c in data.get("contexts", []) if isinstance(c, dict)}
    ctx = contexts.get(current_ctx)
    if not ctx:
        raise ClusterTargetingError("No current context in practice kubeconfig.")
    actual_cluster = ctx.get("context", {}).get("cluster")
    if actual_cluster != cluster_name:
        raise ClusterTargetingError(
            f"Kubeconfig cluster mismatch: expected {cluster_name}, got {actual_cluster}."
        )

