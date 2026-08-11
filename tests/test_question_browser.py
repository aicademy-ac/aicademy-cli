"""Tests for the interactive arrow-key question picker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aicademy_cli.core import question_browser


def test_status_glyph_passed() -> None:
    assert question_browser._status_glyph({"passed": True}) == "✓"


def test_status_glyph_active() -> None:
    assert question_browser._status_glyph({"status": "active"}) == "▸"


def test_status_glyph_unattempted() -> None:
    assert question_browser._status_glyph({}) == "·"


def test_status_glyph_no_entry() -> None:
    assert question_browser._status_glyph(None) == "·"


@pytest.mark.asyncio
async def test_pick_category_returns_selected_value() -> None:
    fake_question = MagicMock()
    fake_question.ask_async = AsyncMock(return_value="cka")
    with patch("questionary.select", return_value=fake_question) as fake_select:
        result = await question_browser.pick_category()

    assert result == "cka"
    fake_select.assert_called_once()
    # 3 real categories + "All categories" -- confirm nothing was dropped.
    choices = fake_select.call_args.kwargs["choices"]
    assert len(choices) == 4


@pytest.mark.asyncio
async def test_pick_category_all_categories_choice_resolves_to_none() -> None:
    """Regression test: questionary.Choice(value=None) doesn't actually
    keep the value as None -- it silently falls back to using the title as
    the value. Picking "All categories" must still resolve to None, not
    the literal string "All categories" (which would wrongly filter)."""
    fake_question = MagicMock()
    fake_question.ask_async = AsyncMock(return_value=question_browser._ALL_CATEGORIES_SENTINEL)
    with patch("questionary.select", return_value=fake_question):
        result = await question_browser.pick_category()

    assert result is None


@pytest.mark.asyncio
async def test_pick_category_cancelled_returns_none() -> None:
    fake_question = MagicMock()
    fake_question.ask_async = AsyncMock(return_value=None)
    with patch("questionary.select", return_value=fake_question):
        result = await question_browser.pick_category()

    assert result is None


@pytest.mark.asyncio
async def test_pick_question_returns_none_for_empty_list() -> None:
    result = await question_browser.pick_question([], {})
    assert result is None


@pytest.mark.asyncio
async def test_pick_question_builds_one_choice_per_question() -> None:
    questions = [
        {"id": "cka-01", "title": "Fix the pod", "level": "beginner"},
        {"id": "cka-02", "title": "Scale a deployment", "level": "intermediate"},
    ]
    progress = {"cka-01": {"passed": True}}

    fake_question = MagicMock()
    fake_question.ask_async = AsyncMock(return_value="cka-02")
    with patch("questionary.select", return_value=fake_question) as fake_select:
        result = await question_browser.pick_question(questions, progress)

    assert result == "cka-02"
    choices = fake_select.call_args.kwargs["choices"]
    assert len(choices) == 2
    assert choices[0].value == "cka-01"
    assert "✓" in choices[0].title
    assert choices[1].value == "cka-02"
    assert "·" in choices[1].title
    assert fake_select.call_args.kwargs["use_search_filter"] is True


@pytest.mark.asyncio
async def test_pick_question_cancelled_returns_none() -> None:
    fake_question = MagicMock()
    fake_question.ask_async = AsyncMock(return_value=None)
    with patch("questionary.select", return_value=fake_question):
        result = await question_browser.pick_question([{"id": "cka-01"}], {})

    assert result is None
