"""Tests for the verify command's result-signing logic and post-pass flow."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, patch

import pytest

from aicademy_cli.commands import verify as verify_module
from aicademy_cli.commands.verify import (
    _prompt_next_step,
    _sign_verification_result,
    _start_next_question,
)


def test_signature_matches_server_canonical_json_for_ascii() -> None:
    check_results = [{"name": "pod-exists", "passed": True, "message": "ok"}]
    signature = _sign_verification_result(
        "secret", "session-1", "cka-01", True, None, check_results
    )

    expected_payload = json.dumps(
        {
            "sessionId": "session-1",
            "questionId": "cka-01",
            "passed": True,
            "checkResults": check_results,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    expected = hmac.new(
        b"secret", expected_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert signature == expected


def test_signature_keeps_non_ascii_literal_not_escaped() -> None:
    """Regression test: the server's canonicalizer (JS JSON.stringify) keeps
    non-ASCII characters literal. Python's json.dumps default (ensure_ascii=True)
    would \\uXXXX-escape them instead, producing a different signature and a
    "Invalid verification signature" error the moment a check message contains
    e.g. a curly quote or accented character.
    """
    check_results = [{"name": "café-check", "passed": False, "message": "caché"}]
    signature = _sign_verification_result(
        "secret", "session-1", "cka-01", False, None, check_results
    )

    # The buggy (ensure_ascii=True) variant would produce a different signature.
    escaped_payload = json.dumps(
        {
            "sessionId": "session-1",
            "questionId": "cka-01",
            "passed": False,
            "checkResults": check_results,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    escaped_signature = hmac.new(
        b"secret", escaped_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert signature != escaped_signature

    literal_payload = json.dumps(
        {
            "sessionId": "session-1",
            "questionId": "cka-01",
            "passed": False,
            "checkResults": check_results,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    literal_signature = hmac.new(
        b"secret", literal_payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert signature == literal_signature


def test_signature_includes_score_only_when_present() -> None:
    check_results: list[dict[str, object]] = []
    with_score = _sign_verification_result("s", "sid", "qid", True, 5, check_results)
    without_score = _sign_verification_result("s", "sid", "qid", True, None, check_results)
    assert with_score != without_score


@pytest.mark.parametrize(
    "user_input,expected",
    [
        ("c", "clear"),
        ("clear", "clear"),
        ("C", "clear"),
        ("n", "next"),
        ("next", "next"),
        ("x", "exit"),
        ("e", "exit"),
        ("", "exit"),
        ("anything-else", "exit"),  # unrecognized input defaults to exit, not a re-prompt loop
    ],
)
def test_prompt_next_step_maps_input(user_input: str, expected: str) -> None:
    with patch.object(verify_module.Prompt, "ask", return_value=user_input):
        assert _prompt_next_step() == expected


@pytest.mark.asyncio
async def test_start_next_question_tears_down_previous_cluster_before_starting() -> None:
    """Regression test: picking [n]ext used to leave the just-finished
    question's KIND cluster running while a second one was created. The old
    cluster (and only the old cluster, by its exact recorded name) must be
    torn down first."""
    fake_get_next = AsyncMock(
        return_value={"nextQuestion": {"id": "cka-02", "title": "Next one"}}
    )
    fake_start = AsyncMock()
    fake_teardown = AsyncMock()
    active_session = {"clusterName": "aicademy-cka-01", "sessionId": "sess-1"}
    with (
        patch.object(verify_module.api, "get_next_question", fake_get_next),
        patch("aicademy_cli.commands.question._start_async", fake_start),
        patch("aicademy_cli.commands.question._teardown_cluster", fake_teardown),
    ):
        await _start_next_question("cka-01", active_session)

    fake_get_next.assert_awaited_once_with("cka-01")
    fake_teardown.assert_awaited_once_with("aicademy-cka-01", "sess-1")
    fake_start.assert_awaited_once_with("cka-02", verbose=False)


@pytest.mark.asyncio
async def test_start_next_question_shows_upgrade_notice_when_locked() -> None:
    fake_get_next = AsyncMock(
        return_value={
            "nextQuestion": None,
            "code": "UPGRADE_REQUIRED",
            "message": "Upgrade to see more.",
            "upgradeUrl": "https://aicademy.ac/pricing",
        }
    )
    with patch.object(verify_module.api, "get_next_question", fake_get_next):
        await _start_next_question("cka-01", {})  # must not raise


@pytest.mark.asyncio
async def test_start_next_question_shows_all_done_when_exhausted() -> None:
    fake_get_next = AsyncMock(
        return_value={"nextQuestion": None, "code": "ALL_COMPLETED", "message": "Nice work!"}
    )
    with patch.object(verify_module.api, "get_next_question", fake_get_next):
        await _start_next_question("cka-01", {})  # must not raise


@pytest.mark.asyncio
async def test_start_next_question_handles_api_error_gracefully() -> None:
    fake_get_next = AsyncMock(side_effect=verify_module.api.APIError("boom", 500))
    with patch.object(verify_module.api, "get_next_question", fake_get_next):
        await _start_next_question("cka-01", {})  # must not raise
