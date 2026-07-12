"""Main content area for the Aicademy TUI."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class ContentContainer(VerticalScroll):
    """Central content area that swaps views based on app state."""

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]Welcome to Aicademy TUI (alpha)[/dim]\n"
            "[dim]Press / to type a command, or ? for help.[/dim]",
            id="content-body",
            markup=True,
        )

    def _set(self, text: str) -> None:
        self.query_one("#content-body", Static).update(text)

    def show_login(self) -> None:
        self._set(
            "[bold red]Not logged in.[/bold red]\n\n"
            "[dim]Type [bold]/login[/bold] to open the browser login flow,\n"
            "or run [bold]aicademy login[/bold] in your shell first.[/dim]"
        )

    def show_help(self) -> None:
        self._set(
            "[bold cyan]Aicademy TUI Help[/bold cyan]\n\n"
            "[bold]Shortcuts[/bold]\n"
            "  [cyan]r[/cyan]  Restart current question\n"
            "  [cyan]n[/cyan]  Next question / list\n"
            "  [cyan]v[/cyan]  Verify solution\n"
            "  [cyan]i[/cyan]  Show instructions\n"
            "  [cyan]c[/cyan]  Clear cluster\n"
            "  [cyan]d[/cyan]  Start Docker\n"
            "  [cyan]k[/cyan]  Open kubectl shell\n"
            "  [cyan]q[/cyan]  Quit TUI\n"
            "  [cyan]/[/cyan]  Command mode\n"
            "  [cyan]?[/cyan]  This help\n\n"
            "[bold]Commands[/bold]\n"
            "  [cyan]/login[/cyan]            Open browser login flow\n"
            "  [cyan]/start <id>[/cyan]       Start a question\n"
            "  [cyan]/verify[/cyan]           Verify current session\n"
            "  [cyan]/clear[/cyan]            Clear current cluster\n"
            "  [cyan]/list[/cyan]             List all questions\n"
            "  [cyan]/next[/cyan]             Go to next question\n"
            "  [cyan]/docker start[/cyan]     Start Docker Desktop\n"
            "  [cyan]/quit[/cyan]             Quit TUI"
        )

    def show_text(self, text: str) -> None:
        self._set(text)

    def show_questions(self, questions: list[dict[str, Any]]) -> None:
        if not questions:
            self._set("[dim]No questions loaded.[/dim]")
            return
        lines = ["[bold]Questions[/bold]\n"]
        for q in questions:
            qid = q.get("id", "?")
            title = q.get("title", "Untitled")
            cat = q.get("categoryTitle", qid.split("-")[0].upper())
            level = q.get("level", "?")
            status = q.get("status", "unattempted")
            if q.get("passed"):
                status_color = "green"
                icon = "x"
            elif status == "active":
                status_color = "yellow"
                icon = ">"
            else:
                status_color = "dim"
                icon = " "
            lines.append(
                f"  [{status_color}][{icon}][/{status_color}] "
                f"[cyan]{qid}[/cyan]  {title}  "
                f"[dim]{cat} {level}[/dim]"
            )
        self._set("\n".join(lines))

    def show_error(self, message: str) -> None:
        self._set(f"[red]Error: {message}[/red]")

    def show_info(self, message: str) -> None:
        self._set(f"[dim]{message}[/dim]")

    def show_dashboard(
        self, user: dict[str, Any] | None, questions: list[dict[str, Any]]
    ) -> None:
        if not user:
            self.show_login()
            return
        name = user.get("name") or user.get("email") or "User"
        xp = user.get("xp", 0)
        total = len(questions)
        completed = sum(
            1 for q in questions if q.get("status") == "completed" or q.get("passed")
        )
        self._set(
            f"[bold]Welcome, {name}[/bold]\n\n"
            f"  XP: [cyan]{xp}[/cyan]\n"
            f"  Questions completed: [cyan]{completed}/{total}[/cyan]\n\n"
            "[dim]Press / to type a command or use shortcuts below.[/dim]"
        )
