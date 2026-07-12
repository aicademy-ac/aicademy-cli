"""Tests for core utilities."""

from __future__ import annotations

import pytest

from aicademy_cli.core.utils import normalize_question_id


@pytest.mark.parametrize(
    ("input_id", "expected"),
    [
        ("cka-01", "cka-01"),
        ("cka-1", "cka-01"),
        ("cka01", "cka-01"),
        ("cka1", "cka-01"),
        ("a1", "cka-01"),
        ("a-1", "cka-01"),
        ("cka-12", "cka-12"),
        ("cka12", "cka-12"),
        ("a12", "cka-12"),
        ("ckad-03", "ckad-03"),
        ("ckad03", "ckad-03"),
        ("ckad3", "ckad-03"),
        ("c3", "ckad-03"),
        ("d3", "ckad-03"),
        ("cks-04", "cks-04"),
        (None, None),
        ("", ""),
        ("foo-bar", "foo-bar"),
    ],
)
def test_normalize_question_id(input_id: str | None, expected: str | None) -> None:
    assert normalize_question_id(input_id) == expected
