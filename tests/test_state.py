"""Tests for the process-wide --verbose flag."""

from __future__ import annotations

from aicademy_cli import state


def test_verbose_defaults_false() -> None:
    assert state.is_verbose() is False


def test_set_verbose_round_trips() -> None:
    state.set_verbose(True)
    assert state.is_verbose() is True
    state.set_verbose(False)
    assert state.is_verbose() is False
