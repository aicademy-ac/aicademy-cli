"""Textual pilot tests for the TUI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Static

from aicademy_cli import config
from aicademy_cli.tui import commands
from aicademy_cli.tui.app import AicademyTUI
from aicademy_cli.tui.widgets.command_bar import CommandBar
from aicademy_cli.tui.widgets.content import ContentContainer
from aicademy_cli.tui.widgets.status_bar import StatusBar


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".aicademy"
    config_file = config_dir / "config.json"
    config_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config, "CONFIG_DIR", config_dir),
        patch.object(config, "CONFIG_FILE", config_file),
    ):
        yield config_file


@pytest.mark.asyncio
async def test_tui_composes_widgets(temp_config: Path) -> None:
    app = AicademyTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#content", ContentContainer)
        assert app.query_one("#command-bar", CommandBar)
        assert app.query_one("#status-bar", StatusBar)


@pytest.mark.asyncio
async def test_tui_shows_login_when_not_authenticated(temp_config: Path) -> None:
    app = AicademyTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.content().show_login()
        await pilot.pause()
        assert app.content().query_one("#content-body", Static) is not None


@pytest.mark.asyncio
async def test_tui_shows_dashboard_when_authenticated(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    app = AicademyTUI()
    async with app.run_test() as pilot:
        app.user = {"name": "Tester", "xp": 50}
        app.questions = [
            {
                "id": "cka-01",
                "title": "Test",
                "categoryTitle": "CKA",
                "level": "easy",
                "status": "unattempted",
                "passed": False,
            }
        ]
        app.active_session = None
        await pilot.pause()
        app.content().show_dashboard(app.user, app.questions)
        await pilot.pause()
        assert app.content().query_one("#content-body", Static) is not None


@pytest.mark.asyncio
async def test_tui_command_bar_focus(temp_config: Path) -> None:
    app = AicademyTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_command()
        await pilot.pause()
        assert app.command_bar().input().has_focus


def test_command_parser() -> None:
    assert commands.parse_command("/start cka-01") == ("start", ["cka-01"], {})
    assert commands.parse_command("  /verify  ") == ("verify", [], {})
    assert commands.parse_command("") == ("", [], {})
    assert commands.normalize_question_arg(["cka1"]) == "cka-01"


def test_is_valid_command() -> None:
    assert commands.is_valid_command("start")
    assert commands.is_valid_command("verify")


def test_complete_command() -> None:
    assert "start" in commands.complete_command("st")
    assert "verify" in commands.complete_command("v")
    assert commands.complete_command("xyz") == []
    assert len(commands.complete_command("")) == len(commands.COMMANDS)


def test_complete_question_id() -> None:
    questions = [
        {"id": "cka-01"},
        {"id": "cka-02"},
        {"id": "ckad-03"},
    ]
    assert "cka-01" in commands.complete_question_id("cka-0", questions)
    assert commands.complete_question_id("ckad", questions) == ["ckad-03"]
    assert commands.complete_question_id("xyz", questions) == []

    assert not commands.is_valid_command("foo")
