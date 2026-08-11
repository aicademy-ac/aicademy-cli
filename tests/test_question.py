"""Tests for the `question list` command's category grouping and progress merge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import respx
import typer
from httpx import Response
from rich.console import Console

from aicademy_cli import api, config
from aicademy_cli.commands import question


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
async def test_list_questions_groups_by_category_and_merges_progress(
    temp_config: Path,
) -> None:
    config.save_config({"token": "test-token"})

    respx.get("https://www.aicademy.ac/api/practice/questions").mock(
        return_value=Response(
            200,
            json={
                "questions": [
                    {
                        "id": "cka-01",
                        "category": "cka",
                        "title": "Fix the pod",
                        "level": "beginner",
                    },
                    {
                        "id": "ckad-01",
                        "category": "ckad",
                        "title": "Build a deployment",
                        "level": "intermediate",
                    },
                ],
                "pagination": {"page": 1, "limit": 20, "total": 2, "totalPages": 1},
            },
        )
    )
    respx.get("https://www.aicademy.ac/api/practice/progress").mock(
        return_value=Response(
            200, json={"progress": {"cka-01": {"status": "completed", "passed": True}}}
        )
    )

    # `question.console` prints straight to stdout by default -- swap in a
    # recording console so we can assert on what would be shown to the user.
    recorder = Console(record=True, width=100)
    with patch.object(question, "console", recorder):
        await question._list_questions_async()

    output = recorder.export_text()
    assert "CKA" in output
    assert "CKAD" in output
    assert "cka-01" in output
    assert "Passed" in output
    assert "Unattempted" in output


@respx.mock
@pytest.mark.asyncio
async def test_list_questions_degrades_gracefully_when_progress_fails(
    temp_config: Path,
) -> None:
    """Progress is a display nicety -- a failure there must not break the list."""
    config.save_config({"token": "test-token"})

    respx.get("https://www.aicademy.ac/api/practice/questions").mock(
        return_value=Response(
            200,
            json={
                "questions": [
                    {"id": "cka-01", "category": "cka", "title": "Fix the pod", "level": "beginner"}
                ],
                "pagination": {"page": 1, "limit": 20, "total": 1, "totalPages": 1},
            },
        )
    )
    respx.get("https://www.aicademy.ac/api/practice/progress").mock(return_value=Response(500))

    recorder = Console(record=True, width=100)
    with patch.object(question, "console", recorder):
        await question._list_questions_async()

    output = recorder.export_text()
    assert "cka-01" in output
    assert "Unattempted" in output


@pytest.mark.asyncio
async def test_start_conflict_confirm_defaults_to_yes(temp_config: Path) -> None:
    """Regression test: closing an existing active session to start a new one
    must default to Yes on a bare Enter, per the intended start flow."""
    err = api.APIError(
        "conflict",
        409,
        {"code": "SESSION_ACTIVE", "activeQuestionId": "cka-01", "activeSessionId": "sess-1"},
    )

    with (
        patch.object(question.typer, "confirm", return_value=False) as fake_confirm,
        pytest.raises(typer.Exit),
    ):
        await question._handle_start_conflict("cka-02", "aicademy-cka-02", err, verbose=False)

    assert fake_confirm.call_args.kwargs.get("default") is True


def test_resolve_category_flag_none_selected() -> None:
    assert question._resolve_category_flag(False, False, False) is None


def test_resolve_category_flag_single_selected() -> None:
    assert question._resolve_category_flag(True, False, False) == "cka"
    assert question._resolve_category_flag(False, True, False) == "ckad"
    assert question._resolve_category_flag(False, False, True) == "cks"


def test_resolve_category_flag_multiple_selected_errors() -> None:
    with pytest.raises(typer.Exit):
        question._resolve_category_flag(True, True, False)


def test_resolve_level_flag_none_selected() -> None:
    assert question._resolve_level_flag(False, False, False, False) is None


def test_resolve_level_flag_single_selected() -> None:
    assert question._resolve_level_flag(True, False, False, False) == "beginner"
    assert question._resolve_level_flag(False, False, False, True) == "expert"


def test_resolve_level_flag_multiple_selected_errors() -> None:
    with pytest.raises(typer.Exit):
        question._resolve_level_flag(False, True, True, False)


@respx.mock
@pytest.mark.asyncio
async def test_list_questions_filters_by_category_and_level(temp_config: Path) -> None:
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/practice/questions").mock(
        return_value=Response(
            200,
            json={
                "questions": [
                    {
                        "id": "cka-01",
                        "category": "cka",
                        "title": "Fix the pod",
                        "level": "beginner",
                    },
                    {
                        "id": "cka-05",
                        "category": "cka",
                        "title": "Advanced networking",
                        "level": "advanced",
                    },
                    {
                        "id": "ckad-01",
                        "category": "ckad",
                        "title": "Build a deployment",
                        "level": "beginner",
                    },
                ],
                "pagination": {"page": 1, "limit": 20, "total": 3, "totalPages": 1},
            },
        )
    )
    respx.get("https://www.aicademy.ac/api/practice/progress").mock(
        return_value=Response(200, json={"progress": {}})
    )

    recorder = Console(record=True, width=100)
    with patch.object(question, "console", recorder):
        await question._list_questions_async(category="cka", level="beginner")

    output = recorder.export_text()
    assert "cka-01" in output
    assert "cka-05" not in output
    assert "ckad-01" not in output


@respx.mock
@pytest.mark.asyncio
async def test_list_questions_filter_with_no_matches_shows_clean_message(
    temp_config: Path,
) -> None:
    config.save_config({"token": "test-token"})
    respx.get("https://www.aicademy.ac/api/practice/questions").mock(
        return_value=Response(
            200,
            json={
                "questions": [
                    {"id": "cka-01", "category": "cka", "title": "Fix the pod", "level": "beginner"}
                ],
                "pagination": {"page": 1, "limit": 20, "total": 1, "totalPages": 1},
            },
        )
    )

    recorder = Console(record=True, width=100)
    with (
        patch.object(question, "console", recorder),
        pytest.raises(typer.Exit),
    ):
        await question._list_questions_async(category="cks")

    assert "No questions match that filter" in recorder.export_text()


@pytest.mark.asyncio
async def test_pick_question_interactively_uses_category_flag_without_prompting(
    temp_config: Path,
) -> None:
    """A --cka/--ckad/--cks flag should skip the interactive category
    prompt entirely."""
    config.save_config({"token": "test-token"})
    questions = [
        {"id": "cka-01", "category": "cka", "title": "Fix the pod", "level": "beginner"},
        {"id": "ckad-01", "category": "ckad", "title": "Build a deployment", "level": "beginner"},
    ]

    with (
        patch.object(question.api, "get_all_questions", return_value=questions),
        patch.object(question.api, "get_progress", return_value={}),
    ):
        from aicademy_cli.core import question_browser

        with patch.object(question_browser, "pick_category") as fake_pick_category:
            with patch.object(
                question_browser, "pick_question", return_value="cka-01"
            ) as fake_pick:
                result = await question._pick_question_interactively(category="cka", level=None)

    fake_pick_category.assert_not_called()
    assert result == "cka-01"
    # Only the cka question should have been offered.
    passed_questions = fake_pick.call_args.args[0]
    assert [q["id"] for q in passed_questions] == ["cka-01"]


@pytest.mark.asyncio
async def test_pick_question_interactively_prompts_for_category_when_not_given(
    temp_config: Path,
) -> None:
    config.save_config({"token": "test-token"})
    questions = [{"id": "cka-01", "category": "cka", "title": "Fix the pod", "level": "beginner"}]

    with (
        patch.object(question.api, "get_all_questions", return_value=questions),
        patch.object(question.api, "get_progress", return_value={}),
    ):
        from aicademy_cli.core import question_browser

        with (
            patch.object(
                question_browser, "pick_category", return_value="cka"
            ) as fake_pick_category,
            patch.object(question_browser, "pick_question", return_value="cka-01"),
        ):
            result = await question._pick_question_interactively(category=None, level=None)

    fake_pick_category.assert_called_once()
    assert result == "cka-01"


@pytest.mark.asyncio
async def test_pick_question_interactively_returns_none_when_no_matches(
    temp_config: Path,
) -> None:
    config.save_config({"token": "test-token"})
    questions = [{"id": "cka-01", "category": "cka", "title": "Fix the pod", "level": "beginner"}]

    with patch.object(question.api, "get_all_questions", return_value=questions):
        result = await question._pick_question_interactively(category="cks", level=None)

    assert result is None
