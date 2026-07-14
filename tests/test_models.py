"""Tests for Pydantic models and validation."""

from __future__ import annotations

import pytest

from aicademy_cli.models import ConfigFileAction, PracticeQuestion


def test_config_file_action_allows_safe_path() -> None:
    action = ConfigFileAction(
        type="config_file",
        container="control-plane",
        path="/etc/kubernetes/manifests/kube-apiserver.yaml",
        content="foo: bar",
    )
    assert action.path == "/etc/kubernetes/manifests/kube-apiserver.yaml"


@pytest.mark.parametrize(
    "path",
    [
        "etc/kubernetes/foo.yaml",
        "../etc/shadow",
        "/etc/passwd",
        "/tmp/foo",
        "/root/.ssh/authorized_keys",
    ],
)
def test_config_file_action_rejects_unsafe_path(path: str) -> None:
    with pytest.raises(ValueError):
        ConfigFileAction(
            type="config_file",
            container="control-plane",
            path=path,
            content="foo: bar",
        )


def test_practice_question_accepts_known_cluster_template() -> None:
    q = PracticeQuestion(
        id="cka-01",
        category="cka",
        subCategory="workloads",
        level="beginner",
        title="Test",
        description="Test",
        scenario="Test",
        tasks=[],
        hints=[],
        tags=[],
        estimatedMinutes=10,
        clusterTemplate="1-node",
    )
    assert q.clusterTemplate == "1-node"


def test_practice_question_rejects_unknown_cluster_template() -> None:
    with pytest.raises(ValueError):
        PracticeQuestion(
            id="cka-01",
            category="cka",
            subCategory="workloads",
            level="beginner",
            title="Test",
            description="Test",
            scenario="Test",
            tasks=[],
            hints=[],
            tags=[],
            estimatedMinutes=10,
            clusterTemplate="5-node",
        )
