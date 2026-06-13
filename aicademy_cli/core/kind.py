import subprocess
import typer
from rich.console import Console

console = Console()

def create_cluster(cluster_name: str) -> None:
    console.print(f"\n[bold]Creating KIND cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    console.print("[dim]This may take 30–90 seconds...[/dim]\n")

    kind_cmd = ["kind", "create", "cluster", "--name", cluster_name]
    try:
        subprocess.run(kind_cmd, check=True)
    except subprocess.CalledProcessError:
        console.print("[red]✗ Failed to create KIND cluster.[/red]")
        console.print("[dim]Make sure Docker is running.[/dim]")
        raise typer.Exit(1)

def delete_cluster(cluster_name: str) -> None:
    console.print(f"[bold]Deleting cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    try:
        subprocess.run(["kind", "delete", "cluster", "--name", cluster_name], check=True)
        console.print("[green]✔ Cluster deleted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠ Could not delete cluster (may not exist).[/yellow]")
