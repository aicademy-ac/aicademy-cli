"""CLI version compatibility helpers."""

from __future__ import annotations

from packaging.version import InvalidVersion, Version

from . import __version__


class IncompatibleCliVersionError(Exception):
    """Raised when the CLI is too old for a question."""


def check_minimum_cli_version(min_version: str | None) -> None:
    """Abort if this CLI is older than the question's minimum required version."""
    if not min_version:
        return
    try:
        required = Version(min_version)
        current = Version(__version__)
    except InvalidVersion as exc:
        raise IncompatibleCliVersionError(
            f"Invalid minimumCliVersion returned by API: {min_version}"
        ) from exc
    if current < required:
        raise IncompatibleCliVersionError(
            f"This question requires aicademy CLI >= {min_version}. "
            "Please upgrade with: pip install --upgrade aicademy"
        )
