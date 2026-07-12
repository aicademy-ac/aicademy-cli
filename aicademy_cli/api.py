"""Async API Client for Aicademy CLI"""

from __future__ import annotations

from typing import Any

import httpx

from . import config

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
    t = token or config.get_token()
    if t:
        return {"Authorization": f"Bearer {t}"}
    return {}


async def _request(method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = await _client.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        raise APIError(f"Network error: {exc}", 0, str(exc)) from exc

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


async def get_sessions() -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/sessions",
        headers=_get_headers(),
        timeout=10,
    )


async def start_session(question_id: str, cluster_name: str) -> dict[str, Any]:
    return await _request(
        "POST",
        f"{config.API_BASE_URL}/api/practice/sessions",
        json={"questionId": question_id, "clusterName": cluster_name},
        headers=_get_headers(),
        timeout=15,
    )


async def get_question(category: str, question_id: str) -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/questions/{category}/{question_id}",
        headers=_get_headers(),
        timeout=10,
    )


async def get_all_questions() -> dict[str, Any]:
    return await _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/questions",
        headers=_get_headers(),
        timeout=10,
    )


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
) -> None:
    payload: dict[str, Any] = {
        "passed": result.get("passed"),
        "message": result.get("message", ""),
        "verificationToken": verification_token,
    }
    score = result.get("score")
    if score is not None:
        payload["score"] = score
    if check_results is not None:
        payload["checkResults"] = check_results

    await _request(
        "POST",
        f"{config.API_BASE_URL}/api/practice/sessions/{session_id}",
        json=payload,
        headers=_get_headers(),
        timeout=10,
    )
