"""CLI command modules for Aicademy."""

from __future__ import annotations

from .auth import app as auth_app
from .legacy import app as legacy_app
from .question import app as question_app
from .tools import app as tools_app

__all__ = ["auth_app", "legacy_app", "question_app", "tools_app"]
