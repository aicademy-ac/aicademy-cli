"""Bottom status bar for the Aicademy TUI."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from textual.reactive import reactive
from textual.widgets import Static

_SEP = " [dim]│[/dim] "


class StatusBar(Static):
    """Persistent status bar: question, progress, Docker, shortcuts."""

    token: reactive[str | None] = reactive(None)
    user: reactive[dict[str, Any] | None] = reactive(None)
    questions: reactive[list[dict[str, Any]]] = reactive([])
    active_session: reactive[dict[str, Any] | None] = reactive(None)
    docker_running: reactive[bool] = reactive(False)
    last_error: reactive[str | None] = reactive(None)

    _DOCKER_CHECK_INTERVAL = 30

    _CATEGORY_ABBREVS = {
        "certified kubernetes administrator": "CKA",
        "certified kubernetes application developer": "CKAD",
        "certified kubernetes security specialist": "CKS",
        "cka": "CKA",
        "ckad": "CKAD",
        "cks": "CKS",
    }

    def on_mount(self) -> None:
        self.set_interval(self._DOCKER_CHECK_INTERVAL, self._kick_docker_check)
        self._kick_docker_check()

    def _kick_docker_check(self) -> None:
        asyncio.create_task(self._check_docker())

    async def _check_docker(self) -> None:
        if not shutil.which("docker"):
            self.docker_running = False
            return
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "info",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            self.docker_running = await proc.wait() == 0
        except Exception:
            self.docker_running = False

    def _abbrev(self, name: str) -> str:
        return self._CATEGORY_ABBREVS.get(
            name.lower(), name.upper()[:4] if name else "?"
        )

    def _progress(self) -> str:
        if not self.questions:
            return ""
        cats: dict[str, tuple[int, int]] = {}
        for q in self.questions:
            cat = self._abbrev(
                q.get("categoryTitle") or q.get("id", "?").split("-")[0]
            )
            done, total = cats.get(cat, (0, 0))
            if q.get("status") == "completed" or q.get("passed"):
                done += 1
            cats[cat] = (done, total + 1)
        xp = (self.user or {}).get("xp", 0)
        parts = [f"XP {xp}"]
        for cat, (done, total) in sorted(cats.items()):
            parts.append(f"{cat} {done}/{total}")
        return _SEP.join(parts)

    def render(self) -> str:
        qid = "--"
        if self.active_session:
            qid = self.active_session.get("question", {}).get("id", "?")
        docker_icon = "●" if self.docker_running else "○"
        docker_color = "green" if self.docker_running else "red"
        progress = self._progress()
        line1 = (
            f"[bold cyan]▣ {qid}[/bold cyan]"
            f"{_SEP}[dim]{progress}[/dim]"
            f"{_SEP}[{docker_color}]{docker_icon} docker[/{docker_color}]"
        )
        line2 = (
            "[dim]  r[/dim] restart"
            "  [dim]n[/dim] next"
            "  [dim]v[/dim] verify"
            "  [dim]i[/dim] info"
            "  [dim]c[/dim] clear"
            "  [dim]k[/dim] shell"
            "  [dim]d[/dim] docker"
            "  [dim]/[/dim] cmd"
            "  [dim]q[/dim] quit"
        )
        return f"{line1}\n{line2}"
