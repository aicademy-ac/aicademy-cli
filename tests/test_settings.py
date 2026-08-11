"""Tests for the `aicademy config` preference commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from aicademy_cli import config
from aicademy_cli.commands.settings import app

runner = CliRunner()


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


def test_show_settings_reports_enabled_by_default(temp_config: Path) -> None:
    result = runner.invoke(app, ["show"])
    assert result.exit_code == 0
    assert "on" in result.stdout


def test_error_reporting_off_then_on(temp_config: Path) -> None:
    result = runner.invoke(app, ["error-reporting", "off"])
    assert result.exit_code == 0
    assert config.is_error_reporting_enabled() is False

    result = runner.invoke(app, ["error-reporting", "on"])
    assert result.exit_code == 0
    assert config.is_error_reporting_enabled() is True


def test_error_reporting_rejects_invalid_state(temp_config: Path) -> None:
    result = runner.invoke(app, ["error-reporting", "maybe"])
    assert result.exit_code == 1


def test_install_aliases_reports_added_and_already_present(temp_config: Path) -> None:
    from aicademy_cli.core.shell_alias import AliasResult

    results = [
        AliasResult("aic", "aicademy", "added", "/home/user/.bashrc"),
        AliasResult("k", "kubectl", "already present", "/home/user/.bashrc"),
    ]
    with patch(
        "aicademy_cli.commands.settings.shell_alias.install_aliases",
        return_value=("bash", results),
    ):
        result = runner.invoke(app, ["install-aliases"])

    assert result.exit_code == 0
    assert "Detected shell: bash" in result.output
    assert "aic" in result.output and "aicademy" in result.output
    assert "already present" in result.output
    assert "Restart your shell" in result.output


def test_install_aliases_shows_manual_steps_when_detection_fails(temp_config: Path) -> None:
    with patch(
        "aicademy_cli.commands.settings.shell_alias.install_aliases", return_value=(None, [])
    ):
        result = runner.invoke(app, ["install-aliases"])

    assert result.exit_code == 1
    assert "Could not detect your shell" in result.output
    assert "Set-Alias aic aicademy" in result.output


def test_install_aliases_shows_manual_steps_for_unsupported_shell(temp_config: Path) -> None:
    with patch(
        "aicademy_cli.commands.settings.shell_alias.install_aliases", return_value=("cmd", [])
    ):
        result = runner.invoke(app, ["install-aliases"])

    assert result.exit_code == 1
    assert "'cmd' isn't a supported shell" in result.output
