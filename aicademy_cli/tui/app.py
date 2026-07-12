"""Main Textual TUI application for Aicademy."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Input

from .. import api, config
from ..core import kind, utils
from . import commands
from .shell import ensure_shell_split, start_docker
from .widgets.command_bar import CommandBar
from .widgets.content import ContentContainer
from .widgets.status_bar import StatusBar


class AicademyTUI(App[None]):
    """Main Textual TUI application for Aicademy."""

    CSS = """
    #content {
        width: 100%;
        height: 1fr;
        border: solid $primary;
        padding: 1 2;
    }
    #footer {
        dock: bottom;
        height: auto;
    }
    #status-bar {
        height: 3;
        background: $panel;
        color: $text;
        padding: 0 2;
        border-top: solid $primary;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "restart", "Restart"),
        ("n", "next", "Next"),
        ("v", "verify", "Verify"),
        ("i", "info", "Instructions"),
        ("c", "clear", "Clear"),
        ("d", "docker", "Docker"),
        ("k", "shell", "Shell"),
        ("slash", "command", "Command"),
        ("question_mark", "help", "Help"),
    ]

    token: reactive[str | None] = reactive(None)
    user: reactive[dict[str, Any] | None] = reactive(None)
    questions: reactive[list[dict[str, Any]]] = reactive([])
    active_session: reactive[dict[str, Any] | None] = reactive(None)
    last_error: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        from textual.containers import Vertical

        yield ContentContainer(id="content")
        with Vertical(id="footer"):
            yield CommandBar(id="command-bar")
            yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self.title = "Aicademy TUI"
        self.sub_title = "Kubernetes exam practice (alpha)"
        self.notify(
            "Aicademy TUI is in alpha. Press / for commands or ? for help.",
            timeout=5,
        )
        asyncio.create_task(self._bootstrap())

    async def _bootstrap(self) -> None:
        self.token = config.get_token()
        if not self.token:
            self.content().show_login()
            return
        await self._load_user()
        await self._load_questions()
        await self._load_active_session()
        self.content().show_dashboard(self.user, self.questions)

    def watch_active_session(self, session: dict[str, Any] | None) -> None:
        self.status_bar().active_session = session

    def watch_user(self, user: dict[str, Any] | None) -> None:
        self.status_bar().user = user

    def watch_questions(self, questions: list[dict[str, Any]]) -> None:
        self.status_bar().questions = questions

    def watch_last_error(self, error: str | None) -> None:
        self.status_bar().last_error = error

    def content(self) -> ContentContainer:
        return self.query_one("#content", ContentContainer)

    def status_bar(self) -> StatusBar:
        return self.query_one("#status-bar", StatusBar)

    def command_bar(self) -> CommandBar:
        return self.query_one("#command-bar", CommandBar)

    def action_command(self) -> None:
        self.command_bar().input().focus()

    async def action_restart(self) -> None:
        if not self.active_session:
            self.notify("No active session. Use /start <id> first.", severity="warning")
            return
        await self._clear_session()
        qid = self.active_session.get("question", {}).get("id") if self.active_session else None
        if qid:
            await self._start_question(qid)

    async def action_next(self) -> None:
        self.content().show_questions(self.questions)

    async def action_verify(self) -> None:
        await self._verify()

    async def action_info(self) -> None:
        await self._show_instructions()

    async def action_clear(self) -> None:
        await self._clear_session()

    async def action_docker(self) -> None:
        await self._start_docker()

    async def action_shell(self) -> None:
        await self._open_shell()

    async def action_help(self) -> None:
        self.content().show_help()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "cmd-input":
            text = event.value.strip()
            self.command_bar().clear()
            self._handle_command(text)

    def _handle_command(self, text: str) -> None:
        cmd, args, _ = commands.parse_command(text)
        if not cmd:
            return
        if not commands.is_valid_command(cmd):
            self.content().show_error(f"Unknown command: /{cmd}")
            return
        if cmd in ("quit", "q"):
            self.exit()
        elif cmd == "help":
            self.content().show_help()
        elif cmd == "login":
            asyncio.create_task(self._login_flow())
        elif cmd == "logout":
            self._logout()
        elif cmd in ("start", "launch"):
            qid = commands.normalize_question_arg(args)
            if not qid:
                self.content().show_error("Usage: /start <question-id>")
                return
            asyncio.create_task(self._start_question(qid))
        elif cmd == "list":
            self.content().show_questions(self.questions)
        elif cmd == "next":
            self.content().show_questions(self.questions)
        elif cmd == "verify":
            asyncio.create_task(self._verify())
        elif cmd == "clear":
            asyncio.create_task(self._clear_session())
        elif cmd in ("instructions", "info"):
            asyncio.create_task(self._show_instructions())
        elif cmd == "docker":
            sub = args[0].lower() if args else "start"
            if sub == "start":
                asyncio.create_task(self._start_docker())
            else:
                status = "running" if self.status_bar().docker_running else "not running"
                self.content().show_info(f"Docker status: {status}")

    async def _load_user(self) -> None:
        try:
            self.user = await api.get_me()
        except api.APIError as e:
            self.last_error = f"Could not load user: {e}"

    async def _load_questions(self) -> None:
        try:
            data = await api.get_all_questions()
            self.questions = data.get("questions", data if isinstance(data, list) else [])
        except api.APIError as e:
            self.last_error = f"Could not load questions: {e}"

    async def _load_active_session(self) -> None:
        cached = config.get_active_session()
        if cached:
            self.active_session = {"session": cached, "question": cached}
            return
        try:
            data = await api.get_sessions()
            sessions = data.get("sessions", data if isinstance(data, list) else [])
            for s in sessions:
                if not s.get("abandonedAt"):
                    qid = s.get("questionId", "?")
                    self.active_session = {"session": s, "question": {"id": qid}}
                    break
        except api.APIError as e:
            self.last_error = f"Could not load sessions: {e}"


    async def _start_question(self, question_id: str) -> None:
        if not self.token:
            self.content().show_login()
            return
        normalized = utils.normalize_question_id(question_id)
        if not normalized:
            self.content().show_error(f"Invalid question ID: {question_id}")
            return
        category = normalized.split("-")[0]
        self.content().show_info(f"Starting {normalized}...")
        try:
            session = await api.start_session(normalized, f"aicademy-{normalized}")
        except api.APIError as e:
            if e.status_code == 409:
                # An existing session is active — clear it and retry once
                self.content().show_info(
                    "Existing session detected. Clearing it..."
                )
                await self._clear_session()
                try:
                    session = await api.start_session(
                        normalized, f"aicademy-{normalized}"
                    )
                except api.APIError as e2:
                    self.content().show_error(f"Failed to start session: {e2}")
                    return
            else:
                self.content().show_error(f"Failed to start session: {e}")
                return
        try:
            question = await api.get_question(category, normalized)
        except api.APIError:
            question = {"id": normalized, "category": category}
        self.set_active(session, question)
        self.content().show_info(f"Started {normalized}.")
        await self._show_instructions()

    async def _verify(self) -> None:
        if not self.active_session:
            self.notify("No active session to verify.", severity="warning")
            return
        session = self.active_session.get("session", {})
        qid = self.active_session.get("question", {}).get("id", "?")
        self.content().show_info("Running verification checks...")
        try:
            result = await kind.verify_session(session, qid)
            self.content().show_text(result)
        except Exception as e:
            self.content().show_error(f"Verification failed: {e}")

    async def _clear_session(self) -> None:
        if not self.active_session:
            self.notify("No active session to clear.", severity="information")
            self.active_session = None
            config.set_active_session(None)
            self.content().show_dashboard(self.user, self.questions)
            return
        session = self.active_session.get("session", {})
        session_id = session.get("id") or session.get("sessionId")
        if session_id:
            try:
                await api.abandon_session(session_id)
            except api.APIError as e:
                self.content().show_error(f"Could not abandon session: {e}")
        kind.delete_cluster(session.get("clusterName", "aicademy"))
        self.active_session = None
        config.set_active_session(None)
        self.content().show_dashboard(self.user, self.questions)
        self.notify("Session cleared.", severity="information")

    async def _show_instructions(self) -> None:
        if not self.active_session:
            self.content().show_info("No active session. Start one with /start <id>")
            return
        qid = self.active_session.get("question", {}).get("id", "?")
        category = qid.split("-")[0]
        try:
            question = await api.get_question(category, qid)
        except api.APIError as e:
            self.content().show_error(f"Could not load instructions: {e}")
            return
        text = question.get("instructions")
        if not text:
            text = question.get("markdown")
        if not text:
            text = "No instructions available."
        self.content().show_text(text)

    async def _login_flow(self) -> None:
        from .. import auth as auth_flow

        await auth_flow.start_device_login()
        self.token = config.get_token()
        if self.token:
            await self._bootstrap()

    def _logout(self) -> None:
        cfg = config.get_config()
        cfg.pop("token", None)
        cfg.pop("active_session", None)
        config.save_config(cfg)
        self.token = None
        self.user = None
        self.active_session = None
        self.content().show_login()
        self.notify("Logged out.", severity="information")

    async def _start_docker(self) -> None:
        try:
            start_docker()
            self.notify("Starting Docker...", severity="information")
        except Exception as e:
            self.notify(f"Docker start failed: {e}", severity="error")

    async def _open_shell(self) -> None:
        kubeconfig = str(config.KUBECONFIG_PATH)
        if not os.path.exists(kubeconfig):
            self.notify("No active cluster. Start a question first.", severity="warning")
            return
        if ensure_shell_split(kubeconfig):
            self.notify("Shell opened with KUBECONFIG set.", severity="information")
        else:
            self.notify("Could not open split shell.", severity="warning")

    def set_active(self, session: dict[str, Any], question: dict[str, Any]) -> None:
        self.active_session = {"session": session, "question": question}
        config.set_active_session(
            {
                "sessionId": session.get("id"),
                "questionId": question.get("id"),
                "category": question.get("category", question.get("id", "").split("-")[0]),
                "clusterName": session.get("clusterName"),
                "verificationToken": session.get("verificationToken"),
            }
        )


def run() -> None:
    """Entry point for the TUI."""
    app = AicademyTUI()
    app.run()
