"""Tests for the authentication flow."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Response

from aicademy_cli import auth, config


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


@respx.mock
@pytest.mark.asyncio
async def test_login_with_token(temp_config: Path) -> None:
    route = respx.get("https://www.aicademy.ac/api/cli-token").mock(
        return_value=Response(200, json={"valid": True, "userId": "u1"})
    )
    await auth.login_with_token("test-token")
    assert config.get_token() == "test-token"
    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_logout_user(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    delete_route = respx.delete("https://www.aicademy.ac/api/cli-token").mock(
        return_value=Response(200, json={"success": True})
    )
    await auth.logout_user()
    assert config.get_token() is None
    assert delete_route.called


@respx.mock
@pytest.mark.asyncio
async def test_whoami(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/me").mock(
        return_value=Response(200, json={"id": "u1", "email": "test@example.com", "xp": 100})
    )
    await auth.whoami()


@respx.mock
@pytest.mark.asyncio
async def test_device_login_flow() -> None:
    respx.get("https://www.aicademy.ac/api/health").mock(
        return_value=Response(200, json={"status": "ok", "db": "ok"})
    )

    respx.get("https://www.aicademy.ac/api/cli-code").mock(
        return_value=Response(200, json={"status": "authorized", "userId": "u1"})
    )
    respx.post("https://www.aicademy.ac/api/cli-code").mock(
        return_value=Response(
            200,
            json={
                "token": "cli-token",
                "userId": "u1",
                "expiresAt": "2026-01-01T00:00:00Z",
            },
        )
    )

    respx.get("https://www.aicademy.ac/api/cli-token").mock(
        return_value=Response(200, json={"valid": True, "userId": "u1"})
    )

    cfg_before = config.get_config()
    with (
        patch.object(config, "API_BASE_URL", "https://www.aicademy.ac"),
        patch("webbrowser.open"),
    ):
        try:
            await auth.start_device_login()
            assert config.get_token() == "cli-token"
        finally:
            config.save_config(cfg_before)
