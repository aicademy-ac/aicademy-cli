"""Tool installation command — installs kubectl, kind, docker via native package managers"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import urlparse

import httpx
import typer
from rich.console import Console
from rich.table import Table

from ..core.prefix_group import PrefixMatchingGroup
from ..core.ui import print_block

console = Console()
app = typer.Typer(
    help="Install and check required tools (kubectl, kind, docker)", cls=PrefixMatchingGroup
)

# ─── Tool definitions ───────────────────────────────────────────────────────────
# Commands are now argv lists where possible to avoid shell injection.
TOOLS: dict[str, dict[str, list[str] | str]] = {
    "kubectl": {
        "check": "kubectl version --client --output=yaml 2>/dev/null",
        "windows": [
            "winget",
            "install",
            "Kubernetes.kubectl",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        "darwin": ["brew", "install", "kubectl"],
        "linux": "__download_binary__",  # handled specially
    },
    "kind": {
        "check": "kind version",
        "windows": [
            "winget",
            "install",
            "Kubernetes.kind",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        "darwin": ["brew", "install", "kind"],
        "linux": "__download_binary__",  # handled specially
    },
    "docker": {
        "check": "docker --version",
        "windows": [
            "winget",
            "install",
            "Docker.DockerDesktop",
            "--accept-source-agreements",
            "--accept-package-agreements",
        ],
        "darwin": ["brew", "install", "--cask", "docker"],
        "linux": "__docker_script__",  # handled specially
    },
}

ALL_TOOLS = list(TOOLS.keys())

# Pinned, HTTPS-only download URLs for Linux binaries.
_LINUX_DOWNLOADS: dict[str, dict[str, str]] = {
    "kubectl": {
        "url": "https://dl.k8s.io/release/v1.30.2/bin/linux/amd64/kubectl",
        "sha256": "c6e9c45ce3f82c90663e3c30db3b27c167e8b19d83ed4048b61c1013f6a7c66e",
        "dest": "/usr/local/bin/kubectl",
    },
    "kind": {
        "url": "https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64",
        "sha256": "1d86e3069ffbe3da9f1a918618aecbc778e00c75f838882d0dfa2d363bc4a68c",
        "dest": "/usr/local/bin/kind",
    },
}


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_to_temp(url: str) -> Path:
    """Download ``url`` to a temporary file and return the path."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"Refusing to download from non-HTTPS URL: {url}")
    resp = httpx.get(url, follow_redirects=True, timeout=60)
    resp.raise_for_status()
    suffix = Path(parsed.path).name or "download"
    fd, tmp = tempfile.mkstemp(suffix=f"-{suffix}")
    with os.fdopen(fd, "wb") as f:
        f.write(resp.content)
    return Path(tmp)


def detect_os() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "darwin"
    return "linux"


def is_installed(tool: str) -> bool:
    binary = tool.split()[0]
    return shutil.which(binary) is not None


def _install_linux_binary(tool_name: str) -> bool:
    """Download a pinned Linux binary to /usr/local/bin with checksum verification."""
    spec = _LINUX_DOWNLOADS.get(tool_name)
    if not spec:
        console.print(f"[red]✗ No Linux download spec for {tool_name}[/red]")
        return False
    tmp = _download_to_temp(spec["url"])
    try:
        actual_sha = _sha256_file(tmp)
        expected_sha = spec["sha256"]
        if actual_sha.lower() != expected_sha.lower():
            console.print(
                f"[red]✗ Checksum mismatch for {tool_name}: "
                f"expected {expected_sha}, got {actual_sha}[/red]"
            )
            return False
        tmp.chmod(0o755)
        subprocess.run(["sudo", "mv", str(tmp), spec["dest"]], check=True)
        console.print(f"[green]✓ {tool_name} installed to {spec['dest']}[/green]")
        return True
    except (subprocess.CalledProcessError, httpx.HTTPError, OSError) as exc:
        console.print(f"[red]✗ Failed to install {tool_name}: {exc}[/red]")
        return False
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _install_linux_docker() -> bool:
    """Install Docker on Linux using the official get.docker.com script (no shell=True pipe)."""
    try:
        script = _download_to_temp("https://get.docker.com")
        console.print("[dim]Running official Docker install script...[/dim]")
        subprocess.run(["sh", str(script)], check=True)
        return True
    except (subprocess.CalledProcessError, httpx.HTTPError, OSError) as exc:
        console.print(f"[red]✗ Failed to install docker: {exc}[/red]")
        return False
    finally:
        try:
            script.unlink(missing_ok=True)
        except OSError:
            pass


def _install_one_tool(tool_name: str, os_type: str, dry_run: bool) -> bool:
    if tool_name not in TOOLS:
        console.print(f"[red]✗ Unknown tool: {tool_name}[/red]")
        return False

    tool = TOOLS[tool_name]
    install_cmd = tool.get(os_type)
    if not install_cmd:
        console.print(f"[red]✗ No install command for {tool_name} on {os_type}[/red]")
        return False

    if is_installed(tool_name):
        console.print(f"[green]✓ {tool_name}[/green] already installed — skipping.")
        return True

    if dry_run:
        console.print(f"[cyan]Would run:[/cyan] [bold]{install_cmd}[/bold]")
        return True

    console.print(f"\n[bold cyan]Installing {tool_name}...[/bold cyan]")

    try:
        if install_cmd == "__download_binary__":
            return _install_linux_binary(tool_name)
        if install_cmd == "__docker_script__":
            return _install_linux_docker()

        # install_cmd is an argv list (no shell=True).
        console.print(f"[dim]$ {' '.join(install_cmd)}[/dim]\n")
        subprocess.run(install_cmd, check=True)
        console.print(f"[green]✓ {tool_name} installed successfully.[/green]")
        return True
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]✗ Failed to install {tool_name}: {exc}[/red]")
        return False


def _install_tools(tools_to_process: Iterable[str], dry_run: bool = False) -> bool:
    os_type = detect_os()
    success_all = True
    for t in tools_to_process:
        success = _install_one_tool(t, os_type, dry_run)
        if not success:
            success_all = False
    return success_all


def _check_tools(tools_to_process: Iterable[str]) -> None:
    from rich import box

    os_type = detect_os()
    table = Table(
        title="🔍  Tool Status",
        title_justify="left",
        border_style="dim",
        box=box.SIMPLE_HEAVY,
    )
    table.add_column("Tool", style="bold", width=10)
    table.add_column("Status", width=13)
    table.add_column("Install Command")
    for t in tools_to_process:
        installed = is_installed(t)
        status = "[green]✓ Installed[/green]" if installed else "[red]✗ Missing[/red]"
        cmd = TOOLS[t].get(os_type, "N/A")
        display = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        table.add_row(t, status, f"[dim]{display}[/dim]")
    console.print(table)


@app.callback(invoke_without_command=True)
def tools(
    ctx: typer.Context,
    install: bool = typer.Option(False, "--install", help="Install all required tools"),
    check: bool = typer.Option(False, "--check", help="Check if required tools are installed"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print install commands without executing"
    ),
    tool: str | None = typer.Argument(
        None,
        help="[Deprecated] Install a single tool: kubectl | kind | docker | all",
    ),
) -> None:
    """
    Install and check required CLI tools.

    Defaults to --check when no flags are provided.

    Examples:
      aicademy tools --check
      aicademy tools --install
    """
    if ctx.invoked_subcommand is not None:
        return

    if tool:
        console.print(
            "[yellow]⚠ Positional tool argument is deprecated. "
            "Use [bold]aicademy tools --install[/bold] instead.[/yellow]"
        )
        tools_to_process = ALL_TOOLS if tool.lower() == "all" else [tool.lower()]
        for t in tools_to_process:
            if t not in TOOLS:
                console.print(f"[red]✗ Unknown tool: {t}.[/red]")
                raise typer.Exit(1)
        success = _install_tools(tools_to_process, dry_run=dry_run)
        if not success:
            raise typer.Exit(1)
        return

    if install:
        os_type = detect_os()
        pkg_mgr = (
            "winget" if os_type == "windows" else "brew" if os_type == "darwin" else "shell script"
        )
        print_block(
            console,
            "🛠 Tool Installation",
            f"[bold]OS detected:[/bold] {os_type}\n"
            f"[bold]Package manager:[/bold] {pkg_mgr}\n"
            f"[bold]Tools:[/bold] {', '.join(ALL_TOOLS)}",
            style="cyan",
        )
        success = _install_tools(ALL_TOOLS, dry_run=dry_run)
        if success:
            print_block(
                console,
                "✓ All tools ready!",
                "You can now run:\n[bold]aicademy start <question-id>[/bold]",
                style="green",
            )
        else:
            console.print(
                "[yellow]⚠ Some tools failed to install. Check the errors above.[/yellow]"
            )
            raise typer.Exit(1)
    else:
        # Default to check
        _check_tools(ALL_TOOLS)


# Backwards-compatible helper used by legacy commands


def install_legacy_tool(
    tool: str,
    check: bool = False,
    dry_run: bool = False,
) -> None:
    """Run the legacy install-tool logic."""
    tools_to_process = ALL_TOOLS if tool.lower() == "all" else [tool.lower()]
    for t in tools_to_process:
        if t not in TOOLS:
            console.print(f"[red]✗ Unknown tool: {t}.[/red]")
            raise typer.Exit(1)

    if check:
        _check_tools(tools_to_process)
    else:
        success = _install_tools(tools_to_process, dry_run=dry_run)
        if not success:
            raise typer.Exit(1)
