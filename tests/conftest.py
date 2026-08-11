"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def fake_keyring() -> Iterator[dict[str, str]]:
    """Replace the OS keychain with an in-memory dict for every test.

    Without this, `config.get_token()`/`set_token()` would hit the real OS
    credential store (Windows Credential Manager, macOS Keychain, ...) on
    whatever machine runs the suite -- writing real "aicademy-cli" entries
    into a developer's actual keychain. Tests must never do that.
    """
    from aicademy_cli import config

    store: dict[str, str] = {}

    def fake_get() -> str | None:
        return store.get(config._KEYRING_USERNAME)

    def fake_set(token: str) -> bool:
        store[config._KEYRING_USERNAME] = token
        return True

    def fake_delete() -> None:
        store.pop(config._KEYRING_USERNAME, None)

    with (
        patch.object(config, "_keyring_get_token", fake_get),
        patch.object(config, "_keyring_set_token", fake_set),
        patch.object(config, "_keyring_delete_token", fake_delete),
    ):
        yield store


@pytest.fixture(autouse=True)
def reset_verbose_state() -> Iterator[None]:
    """`state.py` holds a process-wide flag -- reset it around every test so
    one test enabling --verbose can't leak into the next."""
    from aicademy_cli import state

    state.set_verbose(False)
    yield
    state.set_verbose(False)
