"""Tests for the API client."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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


def test_sign_verification_result_canonical_format() -> None:
    """Verify that _sign_verification_result omits score when score is None."""
    import hashlib
    import hmac
    import json
    from aicademy_cli.commands.verify import _sign_verification_result

    secret = "test-secret"
    session_id = "sess-123"
    question_id = "cka-01"
    check_results = [{"message": "", "name": "check-1", "passed": True}]

    # When score is None, payload MUST NOT include "score" key
    expected_payload = {
        "checkResults": check_results,
        "passed": True,
        "questionId": question_id,
        "sessionId": session_id,
    }
    canonical = json.dumps(expected_payload, sort_keys=True, separators=(",", ":"))
    expected_sig = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    sig = _sign_verification_result(
        secret=secret,
        session_id=session_id,
        question_id=question_id,
        passed=True,
        score=None,
        check_results=check_results,
    )
    assert sig == expected_sig

