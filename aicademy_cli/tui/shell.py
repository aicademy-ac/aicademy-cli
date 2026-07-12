"""Terminal split orchestration for the TUI."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def _kubeconfig_env(kubeconfig: str) -> dict[str, str]:
    """Return env vars for a shell with the session kubeconfig."""
    env = os.environ.copy()
    env["KUBECONFIG"] = kubeconfig
    return env


def ensure_shell_split(kubeconfig: str) -> bool:
    """Try to open a horizontal shell split below the TUI. Return True on success."""
    system = platform.system()

    if system in ("Linux", "Darwin"):
        return _split_tmux(kubeconfig) or _split_new_terminal(kubeconfig, system)

    if system == "Windows":
        return _split_windows_terminal(kubeconfig) or _split_new_terminal(kubeconfig, system)

    return _split_new_terminal(kubeconfig, system)


def _split_tmux(kubeconfig: str) -> bool:
    if not shutil.which("tmux") or not os.environ.get("TMUX"):
        return False
    try:
        subprocess.Popen(
            ["tmux", "split-window", "-v", "-p", "30", f"KUBECONFIG={kubeconfig} bash"]
        )
        return True
    except Exception:
        return False


def _split_windows_terminal(kubeconfig: str) -> bool:
    if not os.environ.get("WT_SESSION") or not shutil.which("wt"):
        return False
    try:
        profile = "Aicademy Shell" if _has_wt_profile("Aicademy Shell") else None
        args = ["wt", "split-pane", "-H", "-s", "0.7"]
        if profile:
            args += ["-p", profile]
        args += ["cmd.exe", "/k", f"set KUBECONFIG={kubeconfig}"]
        subprocess.Popen(args)
        return True
    except Exception:
        return False


def _has_wt_profile(name: str) -> bool:
    try:
        import json

        settings = Path.home() / "AppData" / "Local" / "Packages"
        if not settings.exists():
            return False
        for pkg in settings.iterdir():
            if pkg.name.startswith("Microsoft.WindowsTerminal"):
                state = pkg / "LocalState" / "settings.json"
                if state.exists():
                    data = json.loads(state.read_text(encoding="utf-8"))
                    for p in data.get("profiles", {}).get("list", []):
                        if p.get("name") == name:
                            return True
        return False
    except Exception:
        return False


def _split_new_terminal(kubeconfig: str, system: str) -> bool:
    """Fallback: open a new terminal window."""
    env = _kubeconfig_env(kubeconfig)
    try:
        if system == "Windows":
            subprocess.Popen(["cmd.exe", "/k", f"set KUBECONFIG={kubeconfig}"], env=env)
        else:
            shell = os.environ.get("SHELL", "/bin/bash")
            subprocess.Popen([shell], env=env)
        return True
    except Exception:
        return False


def start_docker() -> None:
    """Attempt to start Docker Desktop / daemon."""
    system = platform.system()
    try:
        if system == "Windows":
            subprocess.Popen(["start", "", "Docker Desktop"], shell=True)
        elif system == "Darwin":
            subprocess.Popen(["open", "-a", "Docker"])
        else:
            subprocess.Popen(["sudo", "systemctl", "start", "docker"])
    except Exception as exc:
        raise RuntimeError(f"Could not start Docker: {exc}") from exc


def launch_tui_with_split() -> None:
    """If not inside a tmux session, create one with a 70/30 split."""
    if not shutil.which("tmux") or os.environ.get("TMUX"):
        return
    try:
        subprocess.Popen(
            [
                "tmux",
                "new-session",
                "-s",
                "aicademy",
                "-n",
                "tui",
                "aicademy",
                "tui",
            ]
        )
    except Exception:
        pass
