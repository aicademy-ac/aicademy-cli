"""Tests for configuration helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aicademy_cli import config


@pytest.fixture
def temp_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".aicademy"
    config_file = config_dir / "config.json"
    config_dir.mkdir(parents=True, exist_ok=True)
    with patch.object(config, "CONFIG_DIR", config_dir), patch.object(
        config, "CONFIG_FILE", config_file
    ):
        yield config_file


def test_config_round_trip(temp_config: Path) -> None:
    assert config.get_config() == {}
    config.save_config({"token": "abc123"})
    assert config.get_token() == "abc123"
    assert config.get_active_session() is None

    session = {"sessionId": "s1", "questionId": "cka-01"}
    config.set_active_session(session)
    assert config.get_active_session() == session

    config.set_active_session(None)
    assert config.get_active_session() is None

    loaded = json.loads(temp_config.read_text(encoding="utf-8"))
    assert loaded["token"] == "abc123"

