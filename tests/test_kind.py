"""Tests for the KIND live progress parsing/streaming helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from aicademy_cli.core import kind

_IMAGE_STAGE = "Ensuring node image (kindest/node:v1.29.0) 🖼"


@pytest.mark.parametrize(
    "raw_line,expected",
    [
        (f"⠋ {_IMAGE_STAGE}", _IMAGE_STAGE),
        (f"✓ {_IMAGE_STAGE}", _IMAGE_STAGE),
        ('Creating cluster "aicademy-cka-01" ...', 'Creating cluster "aicademy-cka-01" ...'),
        ("", ""),
        ("   \n", ""),
    ],
)
def test_extract_stage_text_strips_leading_glyphs(raw_line: str, expected: str) -> None:
    assert kind._extract_stage_text(raw_line) == expected


@pytest.mark.parametrize(
    "raw_line,expected",
    [
        ("✓ Ensuring node image", True),
        ("✗ Starting control-plane", True),
        ("⠋ Ensuring node image", False),
        ("Creating cluster ...", False),
    ],
)
def test_is_stage_complete(raw_line: str, expected: bool) -> None:
    assert kind._is_stage_complete(raw_line) is expected


_DOCKER_ERROR_LINE = (
    'error during connect: Get "http://%2F%2F.%2Fpipe%2FdockerDesktopLinuxEngine/'
    'v1.51/info": open //./pipe/dockerDesktopLinuxEngine: The system cannot find '
    "the file specified."
)


@pytest.mark.parametrize(
    "raw_line,expected",
    [
        ("⠋ Ensuring node image", True),
        ("✓ Ensuring node image", True),
        ("✗ Starting control-plane", True),
        ('Creating cluster "aicademy-cka-01" ...', True),
        ("Deleting cluster aicademy-cka-01", True),
        ("Set kubectl context to kind-aicademy-cka-01", True),
        (_DOCKER_ERROR_LINE, False),  # the exact bug this filter fixes
        ("panic: some internal kind error\n", False),
        ("", False),
        ("   \n", False),
    ],
)
def test_looks_like_kind_protocol_line(raw_line: str, expected: bool) -> None:
    assert kind._looks_like_kind_protocol_line(raw_line) is expected


class _FlakyIterator:
    """Raises once mid-stream, then keeps yielding -- simulates a subprocess
    pipe hitting one bad chunk without dying entirely."""

    def __init__(self, items: list[str]) -> None:
        self._items = iter(items)

    def __iter__(self) -> _FlakyIterator:
        return self

    def __next__(self) -> str:
        item = next(self._items)
        if item == "BAD":
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad byte")
        return item


def test_iter_process_lines_tolerates_decode_errors() -> None:
    result = list(kind._iter_process_lines(_FlakyIterator(["a", "BAD", "b"])))
    assert result == ["a", "b"]


class _FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = iter(lines)
        self.returncode = returncode
        self.terminated = False

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True


def test_run_with_stage_progress_streams_output_and_returns_exit_code(tmp_path: Path) -> None:
    log_file = tmp_path / "kind.log"
    log_file.write_text("", encoding="utf-8")
    lines = [
        'Creating cluster "aicademy-cka-01" ...\n',
        "⠋ Ensuring node image (kindest/node:v1.29.0) 🖼\n",
        "✓ Ensuring node image (kindest/node:v1.29.0) 🖼\n",
        "✓ Preparing nodes 📦\n",
    ]
    fake = _FakeProcess(lines, returncode=0)

    with patch("aicademy_cli.core.kind.subprocess.Popen", return_value=fake):
        rc = kind._run_with_stage_progress(
            ["kind", "create", "cluster"], log_file, "Creating cluster", 6
        )

    assert rc == 0
    content = log_file.read_text(encoding="utf-8")
    assert "Ensuring node image" in content
    assert "Preparing nodes" in content


def test_run_with_stage_progress_never_shows_raw_error_line_live(tmp_path: Path) -> None:
    """Regression test for the reported bug: a raw Docker-connection error
    printed by `kind` before any real stage starts must never be shown as
    the live progress "stage" text (still fully captured in the log file)."""
    log_file = tmp_path / "kind.log"
    log_file.write_text("", encoding="utf-8")
    lines = [
        'Creating cluster "aicademy-cka-01" ...\n',
        f"{_DOCKER_ERROR_LINE}\n",
    ]
    fake = _FakeProcess(lines, returncode=1)

    displayed_stages: list[str] = []
    original_update = kind.Progress.update

    def spy_update(self: kind.Progress, *args: object, **kwargs: object) -> None:
        stage = kwargs.get("stage")
        if isinstance(stage, str):
            displayed_stages.append(stage)
        original_update(self, *args, **kwargs)  # type: ignore[arg-type]

    with (
        patch("aicademy_cli.core.kind.subprocess.Popen", return_value=fake),
        patch.object(kind.Progress, "update", spy_update),
    ):
        rc = kind._run_with_stage_progress(
            ["kind", "create", "cluster"], log_file, "Creating cluster", 6
        )

    assert rc == 1
    assert not any("dockerDesktopLinuxEngine" in s for s in displayed_stages)
    # still fully captured in the log for --verbose reruns / debugging
    assert "dockerDesktopLinuxEngine" in log_file.read_text(encoding="utf-8")


def test_run_with_stage_progress_propagates_nonzero_exit(tmp_path: Path) -> None:
    log_file = tmp_path / "kind.log"
    log_file.write_text("", encoding="utf-8")
    fake = _FakeProcess(["✗ Starting control-plane 🕹️\n"], returncode=1)

    with patch("aicademy_cli.core.kind.subprocess.Popen", return_value=fake):
        rc = kind._run_with_stage_progress(
            ["kind", "create", "cluster"], log_file, "Creating cluster", 6
        )

    assert rc == 1


def test_run_with_stage_progress_missing_binary_exits_cleanly(tmp_path: Path) -> None:
    log_file = tmp_path / "kind.log"
    log_file.write_text("", encoding="utf-8")

    with (
        patch("aicademy_cli.core.kind.subprocess.Popen", side_effect=FileNotFoundError),
        pytest.raises(typer.Exit),
    ):
        kind._run_with_stage_progress(
            ["kind", "create", "cluster"], log_file, "Creating cluster", 6
        )


class _InterruptingIterator:
    """Yields one line, then simulates Ctrl+C on the next read."""

    def __init__(self) -> None:
        self._yielded = False

    def __iter__(self) -> _InterruptingIterator:
        return self

    def __next__(self) -> str:
        if not self._yielded:
            self._yielded = True
            return "⠋ Preparing nodes 📦\n"
        raise KeyboardInterrupt


def test_run_with_stage_progress_terminates_process_on_ctrl_c(tmp_path: Path) -> None:
    """Regression test: Ctrl+C during cluster create/delete must not leave
    `kind` running in the background creating/deleting a cluster nobody is
    tracking anymore."""
    log_file = tmp_path / "kind.log"
    log_file.write_text("", encoding="utf-8")
    fake = _FakeProcess([], returncode=0)
    fake.stdout = _InterruptingIterator()  # type: ignore[assignment]

    with (
        patch("aicademy_cli.core.kind.subprocess.Popen", return_value=fake),
        pytest.raises(KeyboardInterrupt),
    ):
        kind._run_with_stage_progress(
            ["kind", "create", "cluster"], log_file, "Creating cluster", 6
        )

    assert fake.terminated is True
