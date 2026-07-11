"""API Client for Aicademy CLI"""

import httpx
from typing import Any
from . import config

class APIError(Exception):
    def __init__(self, message: str, status_code: int, response_data: dict | str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data

def _get_headers(token: str | None = None) -> dict[str, str]:
    t = token or config.get_token()
    if t:
        return {"Authorization": f"Bearer {t}"}
    return {}

def _request(method: str, url: str, **kwargs) -> dict:
    try:
        resp = httpx.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        raise APIError(f"Network error: {exc}", 0, str(exc))
    
    if resp.status_code >= 400:
        data = resp.text
        try:
            data = resp.json()
        except Exception:
            pass
        raise APIError(f"HTTP {resp.status_code}: {resp.reason_phrase}", resp.status_code, data)
    
    if resp.status_code == 204:
        return None
    try:
        return resp.json()
    except Exception:
        return resp.text

# ─── Auth ───────────────────────────────────────────────────────────────────────

def verify_token(token: str) -> dict:
    return _request(
        "GET",
        f"{config.API_BASE_URL}/api/cli-token",
        headers=_get_headers(token),
        timeout=10,
    )

def logout(token: str) -> None:
    try:
        httpx.delete(
            f"{config.API_BASE_URL}/api/cli-token",
            headers=_get_headers(token),
            timeout=5,
        )
    except httpx.RequestError as exc:
        raise APIError(f"Network error: {exc}", 0, str(exc))

def get_sessions() -> dict:
    return _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/sessions",
        headers=_get_headers(),
        timeout=10,
    )

# ─── Practice ───────────────────────────────────────────────────────────────────

def start_session(question_id: str, cluster_name: str) -> dict:
    return _request(
        "POST",
        f"{config.API_BASE_URL}/api/practice/sessions",
        json={"questionId": question_id, "clusterName": cluster_name},
        headers=_get_headers(),
        timeout=15,
    )

def get_question(category: str, question_id: str) -> dict:
    return _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/questions/{category}/{question_id}",
        headers=_get_headers(),
        timeout=10,
    )

def get_all_questions() -> dict:
    return _request(
        "GET",
        f"{config.API_BASE_URL}/api/practice/questions",
        headers=_get_headers(),
        timeout=10,
    )

def abandon_session(session_id: str) -> None:
    try:
        resp = httpx.patch(
            f"{config.API_BASE_URL}/api/practice/sessions/{session_id}",
            headers=_get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.RequestError as exc:
        raise APIError(f"Network error: {exc}", 0, str(exc))
    except httpx.HTTPStatusError as exc:
        raise APIError(f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}", exc.response.status_code, exc.response.text)

def verify_session(session_id: str, verification_token: str, check_results: list[dict] | None, result: dict) -> None:
    try:
        payload: dict[str, object] = {
            "passed": result.get("passed"),
            "message": result.get("message", ""),
            "score": result.get("score"),
            "verificationToken": verification_token,
        }
        if check_results is not None:
            payload["checkResults"] = check_results
        resp = httpx.post(
            f"{config.API_BASE_URL}/api/practice/sessions/{session_id}",
            json=payload,
            headers=_get_headers(),
            timeout=10,
        )
        resp.raise_for_status()
    except httpx.RequestError as exc:
        raise APIError(f"Network error: {exc}", 0, str(exc))
    except httpx.HTTPStatusError as exc:
        raise APIError(f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}", exc.response.status_code, exc.response.text)
