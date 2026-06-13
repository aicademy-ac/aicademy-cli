"""Tool installation command — installs kubectl, kind, docker via native package managers"""

import sys
import platform
import subprocess
import shutil
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
app = typer.Typer(help="Install required tools (kubectl, kind, docker)")

# ─── Tool definitions ───────────────────────────────────────────────────────────
TOOLS: dict[str, dict] = {
    "kubectl": {
        "check": "kubectl version --client --output=yaml 2>/dev/null",
        "windows": "winget install Kubernetes.kubectl",
        "darwin": "brew install kubectl",
        "linux": "curl -LO https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl && chmod +x kubectl && sudo mv kubectl /usr/local/bin/",
    },
    "kind": {
        "check": "kind version",
        "windows": "winget install Kubernetes.kind",
        "darwin": "brew install kind",
        "linux": "curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64 && chmod +x ./kind && sudo mv ./kind /usr/local/bin/kind",
    },
    "docker": {
        "check": "docker --version",
        "windows": "winget install Docker.DockerDesktop",
        "darwin": "brew install --cask docker",
        "linux": "curl -fsSL https://get.docker.com | sh",
    },
}

ALL_TOOLS = list(TOOLS.keys())


def detect_os() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    else:
        return "linux"


def is_installed(tool: str) -> bool:
    binary = tool.split()[0]
    return shutil.which(binary) is not None


def install_tool(tool_name: str, os_type: str, dry_run: bool) -> bool:
    if tool_name not in TOOLS:
        console.print(f"[red]Unknown tool: {tool_name}[/red]")
        return False

    tool = TOOLS[tool_name]
    install_cmd = tool.get(os_type)
    if not install_cmd:
        console.print(f"[red]No install command for {tool_name} on {os_type}[/red]")
        return False

    if is_installed(tool_name):
        console.print(f"[green]✔ {tool_name}[/green] already installed — skipping.")
        return True

    if dry_run:
        console.print(f"[cyan]Would run:[/cyan] [bold]{install_cmd}[/bold]")
        return True

    console.print(f"\n[bold cyan]Installing {tool_name}...[/bold cyan]")
    console.print(f"[dim]$ {install_cmd}[/dim]\n")

    try:
        result = subprocess.run(
            install_cmd,
            shell=True,
            check=True,
            text=True,
        )
        console.print(f"[green]✔ {tool_name} installed successfully.[/green]")
        return result.returncode == 0
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]✗ Failed to install {tool_name}: {exc}[/red]")
        return False


@app.command("install-tool")
def install(
    tool: str = typer.Argument(
        ...,
        help="Tool to install: kubectl | kind | docker | all",
    ),
    check: bool = typer.Option(False, "--check", help="Check if tools are installed (no install)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print install commands without executing"),
) -> None:
    """
    Install required CLI tools automatically using the system package manager.

    Auto-detects: winget (Windows), brew (macOS), or shell scripts (Linux).

    Examples:
      aicademy install-tool kubectl
      aicademy install-tool all
      aicademy install-tool kind --check
    """
    os_type = detect_os()
    tools_to_process = ALL_TOOLS if tool.lower() == "all" else [tool.lower()]

    for t in tools_to_process:
        if t not in TOOLS:
            console.print(f"[red]Unknown tool: {t}. Choose from: {', '.join(ALL_TOOLS)}, all[/red]")
            raise typer.Exit(1)

    if check:
        table = Table(title="🔍 Tool Status", border_style="dim")
        table.add_column("Tool", style="bold")
        table.add_column("Status")
        table.add_column("Install Command")
        for t in tools_to_process:
            installed = is_installed(t)
            status = "[green]✔ Installed[/green]" if installed else "[red]✗ Missing[/red]"
            cmd = TOOLS[t].get(os_type, "N/A")
            table.add_row(t, status, f"[dim]{cmd}[/dim]")
        console.print(table)
        raise typer.Exit()

    console.print(
        Panel(
            f"[bold]OS detected:[/bold] {os_type}\n"
            f"[bold]Package manager:[/bold] {'winget' if os_type == 'windows' else 'brew' if os_type == 'darwin' else 'shell script'}\n"
            f"[bold]Tools:[/bold] {', '.join(tools_to_process)}",
            title="🛠  Tool Installation",
            border_style="cyan",
        )
    )

    success_all = True
    for t in tools_to_process:
        success = install_tool(t, os_type, dry_run)
        if not success:
            success_all = False

    if success_all:
        console.print(
            Panel(
                "[bold green]All tools ready![/bold green]\n\nYou can now run:\n"
                "[bold]aicademy question start <question-id>[/bold]",
                border_style="green",
            )
        )
    else:
        console.print("[yellow]Some tools failed to install. Check the errors above.[/yellow]")
        raise typer.Exit(1)
