from pathlib import Path
from unittest.mock import patch

import respx
from httpx import Response
from typer.testing import CliRunner

from aicademy_cli import config
from aicademy_cli.main import app

runner = CliRunner()


def test_app_help():
    """Test that the CLI help command works."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Aicademy Practice CLI" in result.stdout


def test_app_version():
    """Test that the CLI version command works."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "aicademy version" in result.stdout


def test_deprecated_commands_hidden_from_help():
    """`install-tool` and the `legacy` group are deprecated -- they must keep
    working (back-compat for existing scripts) but stay out of --help."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "install-tool" not in result.stdout
    assert "legacy" not in result.stdout


@respx.mock
def test_top_level_login_matches_auth_login_behavior(tmp_path: Path) -> None:
    """Regression test: the top-level `login` shortcut used to reimplement a
    subset of `auth login`'s logic and silently dropped the shell-history
    warning for --token. It must now delegate, not duplicate."""
    respx.get("https://www.aicademy.ac/api/cli-token").mock(
        return_value=Response(401, json={"valid": False})
    )
    config_dir = tmp_path / ".aicademy"
    config_file = config_dir / "config.json"
    config_dir.mkdir(parents=True, exist_ok=True)
    with (
        patch.object(config, "CONFIG_DIR", config_dir),
        patch.object(config, "CONFIG_FILE", config_file),
        patch.object(config, "API_BASE_URL", "https://www.aicademy.ac"),
    ):
        result = runner.invoke(app, ["login", "--token", "fake-token"])
    assert "leaks the token to shell history" in result.stdout


def test_install_tool_shortcut_shows_deprecation_warning_once(tmp_path: Path) -> None:
    """Regression test: the top-level shortcut used to print its own copy of
    the deprecation warning *and* delegate to `legacy.install_tool`, which
    printed the same warning again -- showing it twice."""
    result = runner.invoke(app, ["install-tool", "--dry-run", "--check", "kubectl"])
    assert result.stdout.count("is deprecated") == 1
