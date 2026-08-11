"""Best-effort CLI crash reporting.

Unhandled exceptions are reported to the aicademy.ac backend, which forwards
them server-side to Sentry/Axiom -- the CLI never talks to a third-party
error service directly, so no third-party credentials ship in the PyPI
package. Opt-out with `aicademy config error-reporting off`.

Every function here must be safe to call from a crash handler: reporting
itself must never raise, hang, or otherwise get in the way of the CLI
exiting and showing the user what actually went wrong.
"""

from __future__ import annotations

import asyncio
import platform
import traceback
from typing import Any

from . import __version__, config

_REPORT_TIMEOUT = 3  # seconds -- a crash report must never make a crash slower


def _format_traceback(exc: BaseException) -> str:
    formatted = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return formatted[-8000:]  # matches the server's cap; keep the tail (most relevant frames)


def _build_payload(exc: BaseException, command: str | None) -> dict[str, Any]:
    return {
        "message": str(exc) or exc.__class__.__name__,
        "errorType": exc.__class__.__name__,
        "stack": _format_traceback(exc),
        "command": command,
        "cliVersion": __version__,
        "os": platform.system(),
        "pythonVersion": platform.python_version(),
    }


async def _send(payload: dict[str, Any]) -> None:
    import httpx

    async with httpx.AsyncClient(timeout=_REPORT_TIMEOUT) as client:
        await client.post(f"{config.API_BASE_URL}/api/cli-errors", json=payload)


def report_error_sync(exc: BaseException, command: str | None = None) -> None:
    """Fire-and-forget crash report for use in a top-level `except` block.

    Never raises. A silent no-op if the user opted out, if there's no
    network, or if anything about reporting itself goes wrong -- a broken
    telemetry path must never mask (or replace) the real error.
    """
    try:
        if not config.is_error_reporting_enabled():
            return
        payload = _build_payload(exc, command)
        asyncio.run(_send(payload))
    except Exception:
        pass
