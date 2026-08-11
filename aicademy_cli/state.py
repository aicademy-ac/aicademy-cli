"""Process-wide CLI flags that many unrelated modules need to read.

A plain module-level flag (not threaded through every function signature)
mirrors how `config.py` already exposes `API_BASE_URL` -- the pragmatic
choice for a flag set once at startup and read from scattered call sites
across commands, api.py, and the crash handler.
"""

from __future__ import annotations

_verbose = False


def set_verbose(value: bool) -> None:
    global _verbose
    _verbose = value


def is_verbose() -> bool:
    return _verbose
