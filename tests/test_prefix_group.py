"""Tests for unique-prefix command abbreviation (aicademy la -> launch, etc.)."""

from __future__ import annotations

import typer
from typer.testing import CliRunner

from aicademy_cli.core.prefix_group import PrefixMatchingGroup

runner = CliRunner()


def _build_app() -> typer.Typer:
    app = typer.Typer(cls=PrefixMatchingGroup)

    @app.command()
    def login() -> None:
        typer.echo("ran login")

    @app.command()
    def logout() -> None:
        typer.echo("ran logout")

    @app.command("list")
    def list_cmd() -> None:
        typer.echo("ran list")

    @app.command()
    def ls() -> None:
        typer.echo("ran ls")

    @app.command()
    def launch() -> None:
        typer.echo("ran launch")

    @app.command()
    def verify() -> None:
        typer.echo("ran verify")

    return app


def test_exact_match_unaffected() -> None:
    result = runner.invoke(_build_app(), ["login"])
    assert result.exit_code == 0
    assert "ran login" in result.output


def test_unique_prefix_resolves_to_full_command() -> None:
    result = runner.invoke(_build_app(), ["v"])
    assert result.exit_code == 0
    assert "ran verify" in result.output

    result = runner.invoke(_build_app(), ["la"])
    assert result.exit_code == 0
    assert "ran launch" in result.output


def test_ambiguous_prefix_lists_all_candidates() -> None:
    result = runner.invoke(_build_app(), ["l"])
    assert result.exit_code != 0
    assert "ambiguous" in result.output.lower()
    for candidate in ("login", "logout", "list", "ls", "launch"):
        assert candidate in result.output


def test_ambiguous_prefix_with_more_letters_disambiguates() -> None:
    result = runner.invoke(_build_app(), ["log"])
    assert result.exit_code != 0
    assert "login" in result.output
    assert "logout" in result.output
    assert "launch" not in result.output  # narrowed enough to exclude launch

    result = runner.invoke(_build_app(), ["logi"])
    assert result.exit_code == 0
    assert "ran login" in result.output


def test_no_match_falls_through_to_normal_no_such_command_error() -> None:
    result = runner.invoke(_build_app(), ["zzz"])
    assert result.exit_code != 0
    assert "no such command" in result.output.lower()


def test_option_like_first_token_is_not_treated_as_a_command() -> None:
    result = runner.invoke(_build_app(), ["--help"])
    assert result.exit_code == 0


def test_sub_apps_also_get_prefix_matching() -> None:
    """Regression test: abbreviation used to only work at the root app --
    each sub-app (question/auth/tools/config/legacy) built its own plain
    TyperGroup with no cls= override, so `aicademy question la` didn't
    resolve. Confirms both that each sub-app's underlying group really is a
    PrefixMatchingGroup, and that it works end-to-end (via --help, so the
    real command body -- which needs auth/network -- never runs)."""
    from typer.main import get_command

    from aicademy_cli.commands import auth, question, settings, tools

    # legacy.app has exactly one command ("install-tool"), so Typer collapses
    # it to a bare TyperCommand with no group at all -- cls= has nothing to
    # attach to there; it's still set for forward-compatibility if that ever
    # changes, but isn't part of this assertion.
    for sub_app in (auth.app, question.app, tools.app, settings.app):
        assert isinstance(get_command(sub_app), PrefixMatchingGroup)

    result = runner.invoke(question.app, ["la", "--help"])
    assert result.exit_code == 0
    assert "launch" in result.output.lower() or "start" in result.output.lower()
