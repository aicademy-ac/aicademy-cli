"""Command parser for the TUI / command bar."""

from __future__ import annotations

from typing import Any

from aicademy_cli.core import utils

COMMANDS = {
    "login": {"help": "Open browser login flow", "args": []},
    "logout": {"help": "Log out and clear token", "args": []},
    "start": {"help": "Start a question (e.g. /start cka-01)", "args": ["id"]},
    "launch": {"help": "Alias for /start", "args": ["id"]},
    "list": {"help": "List all questions", "args": []},
    "next": {"help": "Go to next question", "args": []},
    "verify": {"help": "Verify current session", "args": []},
    "clear": {"help": "Clear current cluster", "args": []},
    "instructions": {"help": "Show question instructions", "args": []},
    "info": {"help": "Show question instructions", "args": []},
    "docker": {"help": "Docker subcommand (start, status)", "args": ["subcommand"]},
    "help": {"help": "Show this help", "args": []},
    "quit": {"help": "Quit the TUI", "args": []},
    "q": {"help": "Quit the TUI", "args": []},
}


def parse_command(text: str) -> tuple[str, list[str], dict[str, Any]]:
    """Parse a / command string into (cmd, args, kwargs)."""
    text = text.strip()
    if not text:
        return "", [], {}
    if text.startswith("/"):
        text = text[1:]
    parts = text.split()
    if not parts:
        return "", [], {}
    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args, {}


def normalize_question_arg(args: list[str]) -> str | None:
    """Return the first argument normalized to cka-01 style, or None."""
    if not args:
        return None
    return utils.normalize_question_id(args[0])


def help_text() -> str:
    """Return help text for all commands."""
    lines = ["[bold]Available commands[/bold]", ""]
    for cmd, info in sorted(COMMANDS.items()):
        arg_str = " ".join(f"<{a}>" for a in info["args"])
        lines.append(f"[cyan]/{cmd}[/cyan] {arg_str} - {info['help']}")
    return "\n".join(lines)


def is_valid_command(cmd: str) -> bool:
    return cmd in COMMANDS


def complete_command(partial: str) -> list[str]:
    """Return command names that start with the partial string."""
    partial = partial.lower()
    if not partial:
        return sorted(COMMANDS.keys())
    return sorted(c for c in COMMANDS if c.startswith(partial))


def complete_question_id(
    partial: str, questions: list[dict[str, Any]]
) -> list[str]:
    """Return question IDs that start with the partial string."""
    partial = partial.lower()
    if not partial:
        return [q.get("id", "") for q in questions if q.get("id")]
    return [
        q.get("id", "")
        for q in questions
        if q.get("id", "").lower().startswith(partial)
    ]
