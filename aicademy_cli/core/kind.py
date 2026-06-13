import subprocess
import typer
from rich.console import Console
from pathlib import Path
from .. import config

console = Console()

def get_log_path() -> Path:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return config.CONFIG_DIR / "kind.log"

def create_cluster(cluster_name: str, verbose: bool = False) -> None:
    console.print(f"\n[bold]Creating KIND cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    console.print("[dim]This may take 30–90 seconds...[/dim]\n")

    kind_cmd = ["kind", "create", "cluster", "--name", cluster_name]
    log_file = get_log_path()
    try:
        if verbose:
            subprocess.run(kind_cmd, check=True)
        else:
            with open(log_file, "w", encoding="utf-8") as f:
                subprocess.run(kind_cmd, check=True, stdout=f, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        console.print("[red]✗ Failed to create KIND cluster.[/red]")
        console.print("[dim]Make sure Docker is running.[/dim]")
        if not verbose:
            console.print(f"[dim]Check logs for details: {log_file}[/dim]")
        raise typer.Exit(1)

def delete_cluster(cluster_name: str, verbose: bool = False) -> None:
    console.print(f"[bold]Deleting cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    log_file = get_log_path()
    try:
        if verbose:
            subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=True)
        else:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- Deleting cluster {cluster_name} ---\n")
                subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=True, stdout=f, stderr=subprocess.STDOUT)
        console.print("[green]✔ Cluster deleted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠ Could not delete cluster (may not exist).[/yellow]")
