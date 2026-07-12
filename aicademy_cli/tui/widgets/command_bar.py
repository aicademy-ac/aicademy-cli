"""/ command bar with Tab completion for the Aicademy TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Static

from .. import commands

if TYPE_CHECKING:
    from ..app import AicademyTUI


class CommandBar(Vertical):
    """Bottom command input bar (opencode/cline style) with Tab completion."""

    DEFAULT_CSS = """
    CommandBar {
        height: auto;
        background: $boost;
        padding: 0;
        border-top: solid $primary;
    }
    #cmd-row {
        height: 3;
        padding: 0 2;
        background: $boost;
    }
    #cmd-prompt {
        width: auto;
        padding: 0 1;
        content-align: center middle;
        color: $accent;
    }
    #cmd-input {
        width: 1fr;
        border: none;
        background: $boost;
        color: $text;
    }
    #cmd-input:focus {
        border: none;
    }
    #cmd-suggestions {
        height: auto;
        max-height: 6;
        background: $panel;
        color: $text-muted;
        padding: 0 2;
        display: none;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._suggestions: list[str] = []
        self._cycle_index: int = 0

    def compose(self) -> ComposeResult:
        with Horizontal(id="cmd-row"):
            yield Static("[bold cyan]/[/bold cyan] ", id="cmd-prompt")
            yield Input(
                placeholder="type a command, e.g. start cka-01  (Tab to complete)",
                id="cmd-input",
            )
        yield Static("", id="cmd-suggestions")

    def input(self) -> Input:
        return self.query_one("#cmd-input", Input)

    def clear(self) -> None:
        self.input().value = ""
        self._hide_suggestions()

    @property
    def tui_app(self) -> AicademyTUI:
        return self.app  # type: ignore[return-value]

    def _show_suggestions(self, items: list[str]) -> None:
        if not items:
            self._hide_suggestions()
            return
        sug = self.query_one("#cmd-suggestions", Static)
        highlighted = self._cycle_index % len(items)
        lines = []
        for i, item in enumerate(items):
            if i == highlighted:
                lines.append(f"[bold cyan]>> {item}[/bold cyan]")
            else:
                lines.append(f"   {item}")
        sug.update("\n".join(lines))
        sug.styles.display = "block"
        self._suggestions = items

    def _hide_suggestions(self) -> None:
        sug = self.query_one("#cmd-suggestions", Static)
        sug.styles.display = "none"
        sug.update("")
        self._suggestions = []
        self._cycle_index = 0

    def _do_completion(self) -> None:
        text = self.input().value
        parts = text.split(" ")

        if len(parts) == 1:
            partial = parts[0]
            matches = commands.complete_command(partial)
            if not matches:
                self._hide_suggestions()
                return
            if len(matches) == 1:
                self.input().value = matches[0] + " "
                self._hide_suggestions()
            else:
                if self._suggestions != matches:
                    self._cycle_index = 0
                else:
                    self._cycle_index += 1
                chosen = matches[self._cycle_index % len(matches)]
                self.input().value = chosen
                self._show_suggestions(matches)
        else:
            cmd = parts[0].lower()
            partial = parts[-1]
            if cmd in ("start", "launch"):
                matches = commands.complete_question_id(
                    partial, self.tui_app.questions
                )
            elif cmd == "docker":
                matches = [s for s in ("start", "status") if s.startswith(partial)]
            else:
                matches = []
            if not matches:
                self._hide_suggestions()
                return
            if len(matches) == 1:
                prefix = " ".join(parts[:-1])
                self.input().value = prefix + " " + matches[0] + " "
                self._hide_suggestions()
            else:
                if self._suggestions != matches:
                    self._cycle_index = 0
                else:
                    self._cycle_index += 1
                chosen = matches[self._cycle_index % len(matches)]
                prefix = " ".join(parts[:-1])
                self.input().value = prefix + " " + chosen
                self._show_suggestions(matches)

    def on_key(self, event: events.Key) -> None:
        if event.key == "tab":
            event.prevent_default()
            event.stop()
            self._do_completion()
        elif event.key == "escape":
            self._hide_suggestions()
        elif event.key not in ("tab", "escape", "enter"):
            self._cycle_index = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "cmd-input":
            return
        text = event.value
        parts = text.split(" ")
        if len(parts) == 1 and parts[0]:
            matches = commands.complete_command(parts[0])
            if len(matches) > 1:
                self._cycle_index = 0
                self._show_suggestions(matches)
            else:
                self._hide_suggestions()
        elif len(parts) == 2:
            cmd = parts[0].lower()
            partial = parts[1]
            if cmd in ("start", "launch"):
                matches = commands.complete_question_id(
                    partial, self.tui_app.questions
                )
                if len(matches) > 1:
                    self._cycle_index = 0
                    self._show_suggestions(matches)
                else:
                    self._hide_suggestions()
            elif cmd == "docker":
                matches = [s for s in ("start", "status") if s.startswith(partial)]
                if len(matches) > 1:
                    self._cycle_index = 0
                    self._show_suggestions(matches)
                else:
                    self._hide_suggestions()
            else:
                self._hide_suggestions()
        else:
            self._hide_suggestions()

        return self.app  # type: ignore[return-value]
