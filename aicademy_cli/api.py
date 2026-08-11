"""Async API Client for Aicademy CLI"""

from __future__ import annotations

from typing import Any

import httpx

from . import __version__, config, state
from .models import (
    ActiveSessionResponse,
    QuestionDetailResponse,
    StartSessionResponse,
)
from .version import IncompatibleCliVersionError, check_minimum_cli_version

_CLIENT_TIMEOUT = 10
_client: httpx.AsyncClient = httpx.AsyncClient(timeout=_CLIENT_TIMEOUT)


class APIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int,
        response_data: dict[str, Any] | str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


def _get_headers(token: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"X-Aicademy-CLI-Version": __version__}
    t = token or config.get_token()
    if t:
        headers["Authorization"] = f"Bearer {t}"
    return headers


async def _request(method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = await _client.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        # The raw exception (connection internals, resolved IPs, etc.) is
        # implementation detail -- keep it out of the default message and
        # only surface it under --verbose.
        clean_message = "Could not reach the Aicademy server. Check your internet connection."
        detail = str(exc) if state.is_verbose() else clean_message
        raise APIError(clean_message, 0, detail) from exc

    if resp.status_code >= 400:
        data: Any = resp.text
        try:
            data = resp.json()
        except Exception:
            pass
        raise APIError(
            f"HTTP {resp.status_code}: {resp.reason_phrase}",
            resp.status_code,
            data,
        )

    if resp.status_code == 204:
        return None
    try:
        return resp.json()
    except Exception:
        return resp.text


# ─── Auth ───────────────────────────────────────────────────────────────────────


async def verify_token(token: str) -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/cli-token",
        headers=_get_headers(token),
        timeout=10,
    )


async def get_me() -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/me",
        headers=_get_headers(),
        timeout=10,
    )


async def logout(token: str) -> None:
    await _request(
        "DELETE",
        f"{config.API_BASE_URL}/api/cli-token",
        headers=_get_headers(token),
        timeout=5,
    )


async def get_device_status(device_code: str) -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/cli-code",
        params={"device_code": device_code},
        headers={"Accept": "application/json"},
        timeout=10,
    )


async def exchange_device_code(device_code: str) -> dict[str, Any]:
    return await _request(
        "POST",
        f"{config.API_BASE_URL}/api/cli-code",
        json={"device_code": device_code},
        headers={"Accept": "application/json"},
        timeout=10,
    )


# ─── Practice ───────────────────────────────────────────────────────────────────


async def get_sessions() -> ActiveSessionResponse:
    data = await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/sessions",
        headers=_get_headers(),
        timeout=10,
    )
    response = ActiveSessionResponse.model_validate(data)
    try:
        if response.question:
            check_minimum_cli_version(response.question.minimumCliVersion)
    except IncompatibleCliVersionError as exc:
        raise APIError(str(exc), 426, {"upgrade_required": True}) from exc
    return response


async def start_session(question_id: str, cluster_name: str) -> StartSessionResponse:
    data = await _request(
        "POST",
        f"{config.API_BASE_URL}/api/practice/sessions",
        json={"questionId": question_id, "clusterName": cluster_name},
        headers=_get_headers(),
        timeout=15,
    )
    response = StartSessionResponse.model_validate(data)
    try:
        check_minimum_cli_version(response.minimumCliVersion)
    except IncompatibleCliVersionError as exc:
        raise APIError(str(exc), 426, {"upgrade_required": True}) from exc
    return response


async def get_question(category: str, question_id: str) -> QuestionDetailResponse:
    data = await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/questions/{category}/{question_id}",
        headers=_get_headers(),
        timeout=10,
    )
    response = QuestionDetailResponse.model_validate(data)
    try:
        check_minimum_cli_version(response.minimumCliVersion)
    except IncompatibleCliVersionError as exc:
        raise APIError(str(exc), 426, {"upgrade_required": True}) from exc
    return response


_QUESTIONS_PAGE_LIMIT = 20  # server caps `limit` at 20 (Zod schema max)


async def get_all_questions() -> list[dict[str, Any]]:
    """Fetch every practice question across all server pages.

    /api/practice/questions paginates (max 20/page) -- fetching only page 1
    silently truncates the catalog, so walk every page until exhausted.
    """
    questions: list[dict[str, Any]] = []
    page = 1
    while True:
        data = await _request(
            "GET",
            f"{config.API_BASE_URL}/api/practice/questions",
            params={"page": page, "limit": _QUESTIONS_PAGE_LIMIT},
            headers=_get_headers(),
            timeout=10,
        )
        page_questions = data.get("questions", [])
        if not page_questions:
            break
        questions.extend(page_questions)
        total_pages = data.get("pagination", {}).get("totalPages", 1)
        if page >= total_pages:
            break
        page += 1
    return questions


async def get_next_question(current_id: str | None = None) -> dict[str, Any]:
    """Fetch the next question the user can access, walking forward from
    `current_id`. See /api/practice/next for the exact response shape:
    `{"nextQuestion": {...}}` or `{"nextQuestion": None, "code": ..., "message": ...}`.
    """
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/next",
        params={"current": current_id} if current_id else None,
        headers=_get_headers(),
        timeout=10,
    )


async def get_progress() -> dict[str, Any]:
    """Fetch the current user's pass/fail progress, keyed by question ID."""
    data = await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/progress",
        headers=_get_headers(),
        timeout=10,
    )
    return data.get("progress", {})


async def abandon_session(session_id: str) -> None:
    await _request(
        "PATCH",
        f"{config.API_BASE_URL}/api/practice/sessions/{session_id}",
        headers=_get_headers(),
        timeout=10,
    )


async def verify_session(
    session_id: str,
    verification_token: str,
    check_results: list[dict[str, Any]] | None,
    result: dict[str, Any],
    signature: str,
) -> None:
    payload: dict[str, Any] = {
        "passed": result.get("passed"),
        "message": result.get("message", ""),
        "verificationToken": verification_token,
        "signature": signature,
    }
    score = result.get("score")
    if score is not None:
        payload["score"] = score
    if check_results is not None:
        payload["checkResults"] = check_results

    await _request(
        "POST",
        f"{config.API_BASE_URL}/api/practice/sessions/{session_id}/verify",
        json=payload,
        headers=_get_headers(),
        timeout=10,
    )

