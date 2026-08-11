"""KIND cluster lifecycle helpers."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .. import config
from .cluster_context import ClusterTargetingError

console = Console()

# kind reports progress as a sequence of spinner lines, one per stage, each
# repeatedly rewritten in place (\r) while running and finally marked done
# with a leading ✓ (or ✗ on failure) once it completes -- e.g.:
#   ⠋ Ensuring node image (kindest/node:v1.29.0) 🖼
#   ✓ Ensuring node image (kindest/node:v1.29.0) 🖼
# Stripping the leading glyph/whitespace leaves a human-readable stage name
# we can show as our own progress text, independent of kind's own spinner
# rendering (which we don't want mixed with ours).
_LEADING_GLYPH_RE = re.compile(r'^[^\w"]+')

_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_KNOWN_BANNER_PREFIXES = ("Creating cluster", "Deleting cluster", "Set kubectl context")

# Ensuring node image, Preparing nodes, Writing configuration,
# Starting control-plane, Installing CNI, Installing StorageClass -- the
# common single-control-plane path. Multi-node templates add a "Joining
# worker nodes" stage; waitForReady adds one more. This is only used to size
# the bar -- if kind reports more stages than expected, the bar's total is
# simply extended rather than the display getting stuck or looking wrong.
_ESTIMATED_CREATE_STAGES = 6


def get_log_path() -> Path:
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return config.CONFIG_DIR / "kind.log"


def _extract_stage_text(raw_line: str) -> str:
    return _LEADING_GLYPH_RE.sub("", raw_line).strip()


def _is_stage_complete(raw_line: str) -> bool:
    return "✓" in raw_line or "✗" in raw_line


def _looks_like_kind_protocol_line(raw_line: str) -> bool:
    """True only for lines matching kind's own stage-progress protocol
    (spinner frames, checkmark/cross completion markers, or its known
    banner lines). A fatal startup error (e.g. "can't reach Docker") is
    printed *without* any of these markers -- this is what keeps that raw
    text out of the live display (it's still written to the log file
    either way) instead of showing internal detail to the user by default.
    """
    stripped = raw_line.lstrip()
    if not stripped:
        return False
    if stripped[0] in _SPINNER_CHARS or stripped[0] in ("✓", "✗"):
        return True
    return stripped.startswith(_KNOWN_BANNER_PREFIXES)


def _iter_process_lines(pipe: Iterable[str]) -> Iterable[str]:
    """Yield each line from a subprocess pipe, tolerating mid-stream decode
    hiccups instead of losing the rest of the output to one bad line."""
    iterator = iter(pipe)
    while True:
        try:
            line = next(iterator)
        except StopIteration:
            return
        except (UnicodeDecodeError, ValueError):
            continue
        yield line


def _run_with_stage_progress(
    cmd: list[str],
    log_file: Path,
    description: str,
    estimated_total: int | None,
) -> int:
    """Run `cmd`, live-updating a Rich progress display from its own stage
    output, and return its exit code. Every line is also appended to
    `log_file` verbatim so `--verbose` reruns / support requests still have
    the full transcript. A display/parsing hiccup here must never affect the
    underlying operation -- worst case, the bar just shows less detail.
    """
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        console.print(f"[red]'{cmd[0]}' not found on PATH.[/red]")
        raise typer.Exit(1) from None

    completed_stages = 0
    try:
        with (
            open(log_file, "a", encoding="utf-8") as log,
            Progress(
                SpinnerColumn(),
                TextColumn("[bold]{task.description}[/bold]"),
                BarColumn(),
                TextColumn("{task.fields[stage]}", style="dim"),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress,
        ):
            task = progress.add_task(description, total=estimated_total, stage="starting...")
            assert process.stdout is not None
            for raw_line in _iter_process_lines(process.stdout):
                log.write(raw_line if raw_line.endswith("\n") else raw_line + "\n")
                if not _looks_like_kind_protocol_line(raw_line):
                    continue  # logged above; never shown live -- see docstring
                stage_text = _extract_stage_text(raw_line)
                if not stage_text:
                    continue
                if _is_stage_complete(raw_line):
                    completed_stages += 1
                    if estimated_total is not None and completed_stages > estimated_total:
                        progress.update(task, total=completed_stages)
                    progress.update(task, completed=completed_stages, stage=stage_text)
                else:
                    progress.update(task, stage=stage_text)

            process.wait()
            if estimated_total is not None:
                progress.update(task, completed=max(completed_stages, estimated_total))
    except KeyboardInterrupt:
        # Ctrl+C must not leave `kind` running in the background creating/
        # deleting a cluster nobody is tracking anymore -- stop it, then let
        # the interrupt propagate so cli_entry() can print a clean message.
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise

    return process.returncode


def create_cluster(
    cluster_name: str,
    config_content: str | None = None,
    verbose: bool = False,
) -> None:
    console.print(f"\n[bold]Creating KIND cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    if verbose:
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
            result = subprocess.run(kind_cmd, check=False)
            returncode = result.returncode
        else:
            log_file.write_text("", encoding="utf-8")  # fresh log per run, same as before
            returncode = _run_with_stage_progress(
                kind_cmd, log_file, "Creating cluster", _ESTIMATED_CREATE_STAGES
            )
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, kind_cmd)
    except subprocess.CalledProcessError:
        console.print("[red]✗ Failed to create KIND cluster.[/red]")
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
            "[red]✗ Could not export kubeconfig for the practice cluster. "
            "Aborting to avoid targeting the default cluster.[/red]"
        )
        raise typer.Exit(1) from exc


def delete_cluster(cluster_name: str, verbose: bool = False) -> None:
    console.print(f"[bold]Deleting cluster:[/bold] [cyan]{cluster_name}[/cyan]")
    kind_cmd = ["kind", "delete", "cluster", "--name", cluster_name]
    log_file = get_log_path()
    try:
        if verbose:
            result = subprocess.run(kind_cmd, check=False)
            returncode = result.returncode
        else:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n--- Deleting cluster {cluster_name} ---\n")
            returncode = _run_with_stage_progress(kind_cmd, log_file, "Deleting cluster", None)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, kind_cmd)
        console.print("[green]✓ Cluster deleted.[/green]")
    except subprocess.CalledProcessError:
        console.print("[yellow]⚠ Could not delete cluster (may not exist).[/yellow]")


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

