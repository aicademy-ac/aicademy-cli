"""Tests for core utilities."""

from __future__ import annotations

import pytest

from aicademy_cli.core.utils import (
    is_valid_category,
    is_valid_cluster_name,
    is_valid_question_id,
    is_valid_session_id,
    normalize_question_id,
)


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
        ("cks4", "cks-04"),
        ("s4", "cks-04"),
        (None, None),
        ("", None),
        ("foo-bar", None),
        ("../../../etc/passwd", None),
    ],
)
def test_normalize_question_id(input_id: str | None, expected: str | None) -> None:
    assert normalize_question_id(input_id) == expected


@pytest.mark.parametrize(
    ("qid", "expected"),
    [
        ("cka-01", True),
        ("ckad-12", True),
        ("cks-99", True),
        ("CKA-01", True),
        ("cka-1", False),
        ("foo-bar", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_question_id(qid: str | None, expected: bool) -> None:
    assert is_valid_question_id(qid) is expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("aicademy-cka-01", True),
        ("aicademy-ckad-12", True),
        ("aicademy-cks-99", True),
        ("kind-aicademy-cka-01", False),
        ("aicademy-foo-01", False),
        ("production-cluster", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_cluster_name(name: str | None, expected: bool) -> None:
    assert is_valid_cluster_name(name) is expected


@pytest.mark.parametrize(
    ("sid", "expected"),
    [
        ("550e8400-e29b-41d4-a716-446655440000", True),
        ("not-a-uuid", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_session_id(sid: str | None, expected: bool) -> None:
    assert is_valid_session_id(sid) is expected


@pytest.mark.parametrize(
    ("cat", "expected"),
    [
        ("cka", True),
        ("ckad", True),
        ("cks", True),
        ("CKA", True),
        ("foo", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_category(cat: str | None, expected: bool) -> None:
    assert is_valid_category(cat) is expected
