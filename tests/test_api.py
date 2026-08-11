"""Tests for the API client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from httpx import Response

from aicademy_cli import api, config


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
async def test_verify_session_posts_to_verify_endpoint(temp_config: Path) -> None:
    """Regression test: verify_session must POST to /sessions/{id}/verify."""
    config.save_config({"token": "test-token"})
    route = respx.post(
        "https://www.aicademy.ac/api/practice/sessions/sess-123/verify"
    ).mock(return_value=Response(200, json={"success": True, "result": {"passed": True}}))

    await api.verify_session(
        session_id="sess-123",
        verification_token="tok-123",
        check_results=[{"name": "check-1", "passed": True, "message": ""}],
        result={"passed": True, "message": "All checks passed"},
        signature="sig-123",
    )

    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-token"
    body = route.calls.last.request.content
    assert b'"verificationToken":"tok-123"' in body
    assert b'"checkResults"' in body
    assert b'"signature":"sig-123"' in body


@respx.mock
@pytest.mark.asyncio
async def test_abandon_session_patches_session_endpoint(temp_config: Path) -> None:
    """Ensure abandon_session still uses the correct PATCH endpoint."""
    config.save_config({"token": "test-token"})
    route = respx.patch("https://www.aicademy.ac/api/practice/sessions/sess-123").mock(
        return_value=Response(200, json={"success": True})
    )

    await api.abandon_session("sess-123")

    assert route.called


@respx.mock
@pytest.mark.asyncio
async def test_get_all_questions_paginates_through_all_pages(temp_config: Path) -> None:
    """Regression test: the server caps `limit` at 20/page -- page 1 alone
    must not silently truncate the catalog."""
    config.save_config({"token": "test-token"})

    def responder(request: httpx.Request) -> Response:
        page = int(request.url.params.get("page", "1"))
        pages = {
            1: {
                "questions": [{"id": "cka-01"}, {"id": "cka-02"}],
                "pagination": {"page": 1, "limit": 2, "total": 3, "totalPages": 2},
            },
            2: {
                "questions": [{"id": "cka-03"}],
                "pagination": {"page": 2, "limit": 2, "total": 3, "totalPages": 2},
            },
        }
        return Response(200, json=pages[page])

    route = respx.get("https://www.aicademy.ac/api/practice/questions").mock(
        side_effect=responder
    )

    questions = await api.get_all_questions()

    assert [q["id"] for q in questions] == ["cka-01", "cka-02", "cka-03"]
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_get_progress_returns_progress_dict(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/practice/progress").mock(
        return_value=Response(
            200, json={"progress": {"cka-01": {"status": "completed", "passed": True}}}
        )
    )

    progress = await api.get_progress()

    assert progress == {"cka-01": {"status": "completed", "passed": True}}


@respx.mock
@pytest.mark.asyncio
async def test_network_error_message_is_clean_by_default(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/me").mock(side_effect=httpx.ConnectError("boom"))

    with pytest.raises(api.APIError) as exc_info:
        await api.get_me()

    clean = "Could not reach the Aicademy server. Check your internet connection."
    assert str(exc_info.value) == clean
    assert exc_info.value.response_data == clean
    assert "boom" not in str(exc_info.value)


@respx.mock
@pytest.mark.asyncio
async def test_network_error_shows_raw_detail_when_verbose(temp_config: Path) -> None:
    from aicademy_cli import state

    state.set_verbose(True)
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/me").mock(
        side_effect=httpx.ConnectError("connection refused: boom")
    )

    with pytest.raises(api.APIError) as exc_info:
        await api.get_me()

    assert "connection refused: boom" in str(exc_info.value.response_data)
