"""Tests for opt-out crash reporting: config flags and the report_error_sync path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from typer.testing import CliRunner

from aicademy_cli import config, error_reporting, main

runner = CliRunner()


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".aicademy"
    config_file = config_dir / "config.json"
    config_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config, "CONFIG_DIR", config_dir),
        patch.object(config, "CONFIG_FILE", config_file),
        patch.object(config, "API_BASE_URL", "https://www.aicademy.ac"),
    ):
        yield config_file


def test_error_reporting_enabled_by_default(temp_config: Path) -> None:
    assert config.is_error_reporting_enabled() is True


def test_error_reporting_can_be_disabled(temp_config: Path) -> None:
    config.set_error_reporting(False)
    assert config.is_error_reporting_enabled() is False
    config.set_error_reporting(True)
    assert config.is_error_reporting_enabled() is True


def test_notice_shown_flag_round_trips(temp_config: Path) -> None:
    assert config.error_reporting_notice_shown() is False
    config.mark_error_reporting_notice_shown()
    assert config.error_reporting_notice_shown() is True


@respx.mock
def test_report_error_sync_posts_when_enabled(temp_config: Path) -> None:
    config.set_error_reporting(True)
    route = respx.post("https://www.aicademy.ac/api/cli-errors").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    error_reporting.report_error_sync(ValueError("boom"), command="start")

    assert route.called
    body = route.calls.last.request.content
    assert b'"errorType":"ValueError"' in body
    assert b'"command":"start"' in body


@respx.mock
def test_report_error_sync_is_a_noop_when_disabled(temp_config: Path) -> None:
    config.set_error_reporting(False)
    route = respx.post("https://www.aicademy.ac/api/cli-errors").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    error_reporting.report_error_sync(ValueError("boom"))

    assert not route.called


@respx.mock
def test_report_error_sync_never_raises_on_network_failure(temp_config: Path) -> None:
    config.set_error_reporting(True)
    respx.post("https://www.aicademy.ac/api/cli-errors").mock(
        side_effect=httpx.ConnectError("offline")
    )

    # Must not raise -- a broken telemetry path can never break the CLI.
    error_reporting.report_error_sync(ValueError("boom"))


@pytest.mark.parametrize("argv", [["--version"], ["-V"], ["--help"], ["-h"], []])
def test_error_reporting_notice_skipped_for_silent_flags(
    temp_config: Path, argv: list[str]
) -> None:
    """`aicademy --version`/`--help` output must never gain an extra line --
    scripts and CI parse it directly."""
    main._maybe_show_error_reporting_notice(argv)
    assert config.error_reporting_notice_shown() is False


def test_error_reporting_notice_shown_for_real_subcommands(temp_config: Path) -> None:
    main._maybe_show_error_reporting_notice(["list"])
    assert config.error_reporting_notice_shown() is True


def test_cli_entry_reports_and_shows_clean_message_by_default(temp_config: Path) -> None:
    """Default (non-verbose): the exception is reported and logged, but the
    console only sees one clean line + a log pointer -- no traceback."""
    config.mark_error_reporting_notice_shown()  # skip the first-run notice for this test

    def boom() -> None:
        raise RuntimeError("kaboom")

    with (
        patch.object(main, "app", boom),
        patch("aicademy_cli.error_reporting.report_error_sync") as mock_report,
        pytest.raises(SystemExit) as exc_info,
    ):
        main.cli_entry()

    assert exc_info.value.code == 1
    mock_report.assert_called_once()
    assert isinstance(mock_report.call_args.args[0], RuntimeError)

    log_path = config.CONFIG_DIR / "aicademy.log"
    assert log_path.exists()
    assert "RuntimeError: kaboom" in log_path.read_text(encoding="utf-8")


def test_cli_entry_reraises_with_full_traceback_when_verbose(temp_config: Path) -> None:
    """--verbose: the exception still propagates so Typer's own pretty
    traceback renders, same as before this change."""
    from aicademy_cli import state

    config.mark_error_reporting_notice_shown()
    state.set_verbose(True)

    def boom() -> None:
        raise RuntimeError("kaboom")

    with (
        patch.object(main, "app", boom),
        patch("aicademy_cli.error_reporting.report_error_sync") as mock_report,
        pytest.raises(RuntimeError, match="kaboom"),
    ):
        main.cli_entry()

    mock_report.assert_called_once()


def test_cli_entry_handles_ctrl_c_cleanly(temp_config: Path) -> None:
    """Ctrl+C must exit with the conventional 128+SIGINT code and a clean
    message -- not a raw Python traceback, and not go through crash reporting
    (it's not a bug, it's the user asking to stop)."""
    config.mark_error_reporting_notice_shown()

    def interrupted() -> None:
        raise KeyboardInterrupt

    with (
        patch.object(main, "app", interrupted),
        patch("aicademy_cli.error_reporting.report_error_sync") as mock_report,
        pytest.raises(SystemExit) as exc_info,
    ):
        main.cli_entry()

    assert exc_info.value.code == 130
    mock_report.assert_not_called()
