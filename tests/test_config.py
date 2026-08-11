"""Tests for configuration helpers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from aicademy_cli import config


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


def test_config_round_trip(temp_config: Path) -> None:
    assert config.get_config() == {}
    assert config.get_active_session() is None

    session = {"sessionId": "s1", "questionId": "cka-01"}
    config.set_active_session(session)
    assert config.get_active_session() == session

    config.set_active_session(None)
    assert config.get_active_session() is None


def test_set_get_delete_token_via_keyring(temp_config: Path) -> None:
    """`fake_keyring` (conftest, autouse) makes the OS keychain always succeed."""
    assert config.get_token() is None

    in_keychain = config.set_token("abc123")
    assert in_keychain is True
    assert config.get_token() == "abc123"

    # A keychain-backed token must never be duplicated into the plaintext file.
    loaded = json.loads(temp_config.read_text(encoding="utf-8"))
    assert "token" not in loaded

    config.delete_token()
    assert config.get_token() is None


def test_token_falls_back_to_file_when_keyring_unavailable(temp_config: Path) -> None:
    with (
        patch.object(config, "_keyring_get_token", lambda: None),
        patch.object(config, "_keyring_set_token", lambda token: False),
        patch.object(config, "_keyring_delete_token", lambda: None),
    ):
        in_keychain = config.set_token("fallback-token")
        assert in_keychain is False
        assert config.get_token() == "fallback-token"

        loaded = json.loads(temp_config.read_text(encoding="utf-8"))
        assert loaded["token"] == "fallback-token"

        config.delete_token()
        assert config.get_token() is None


def test_is_session_expired_true_after_max_age() -> None:
    started = datetime.now(timezone.utc) - timedelta(hours=config.SESSION_MAX_AGE_HOURS + 1)
    session = {"startedAt": started.isoformat().replace("+00:00", "Z")}
    assert config.is_session_expired(session) is True


def test_is_session_expired_false_within_max_age() -> None:
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    session = {"startedAt": started.isoformat().replace("+00:00", "Z")}
    assert config.is_session_expired(session) is False


def test_is_session_expired_false_when_missing_started_at() -> None:
    """Sessions cached by an older CLI version (no startedAt field) must not
    be treated as expired -- there's no data to judge them by."""
    assert config.is_session_expired({}) is False


def test_is_session_expired_false_for_unparseable_timestamp() -> None:
    assert config.is_session_expired({"startedAt": "not-a-date"}) is False


def test_legacy_file_token_is_migrated_into_keyring(temp_config: Path) -> None:
    """A token saved by an older CLI version (plain config-file field) should be
    picked up transparently and migrated into the OS keychain on first read."""
    config.save_config({"token": "legacy-token"})

    assert config.get_token() == "legacy-token"

    loaded = json.loads(temp_config.read_text(encoding="utf-8"))
    assert "token" not in loaded
