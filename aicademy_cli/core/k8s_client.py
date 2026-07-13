"""Kubernetes SDK wrapper for practice-cluster resource operations."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from kubernetes import client, config, utils
from kubernetes.client.rest import ApiException

from .cluster_context import load_practice_kube_config


class K8sClientError(Exception):
    """Raised when a Kubernetes SDK operation fails."""


def _load_config(kubeconfig: Path) -> None:
    """Load the given kubeconfig into the Kubernetes SDK."""
    config.load_kube_config(config_file=str(kubeconfig))


def apply_manifests(kubeconfig: Path, manifests: list[str]) -> None:
    """Apply YAML manifest strings to the practice cluster."""
    _load_config(kubeconfig)
    for manifest in manifests:
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as tmp:
            tmp.write(manifest)
            tmp_path = tmp.name
        try:
            utils.create_from_yaml(
                client.ApiClient(),
                tmp_path,
            )
        except ApiException as exc:
            raise K8sClientError(f"Failed to apply manifest: {exc.reason}") from exc
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def create_resources(kubeconfig: Path, resources: list[dict[str, Any]]) -> None:
    """Create Kubernetes resources from dict objects."""
    _load_config(kubeconfig)
    for resource in resources:
        try:
            utils.create_from_dict(client.ApiClient(), resource)
        except ApiException as exc:
            raise K8sClientError(f"Failed to create resource: {exc.reason}") from exc


def label_node(kubeconfig: Path, name: str, labels: dict[str, str]) -> None:
    """Add labels to a cluster node."""
    _load_config(kubeconfig)
    core_v1 = client.CoreV1Api()
    try:
        node = core_v1.read_node(name)
        merged = (node.metadata.labels or {}).copy()
        merged.update(labels)
        body = {"metadata": {"labels": merged}}
        core_v1.patch_node(name, body)
    except ApiException as exc:
        raise K8sClientError(f"Failed to label node {name}: {exc.reason}") from exc


def taint_node(
    kubeconfig: Path,
    name: str,
    taints: list[dict[str, Any]],
) -> None:
    """Add taints to a cluster node."""
    _load_config(kubeconfig)
    core_v1 = client.CoreV1Api()
    try:
        node = core_v1.read_node(name)
        existing = node.spec.taints or []
        formatted = [
            client.V1Taint(
                key=t.get("key"),
                value=t.get("value"),
                effect=t.get("effect"),
            )
            for t in taints
        ]
        body = {"spec": {"taints": existing + formatted}}
        core_v1.patch_node(name, body)
    except ApiException as exc:
        raise K8sClientError(f"Failed to taint node {name}: {exc.reason}") from exc


__all__ = [
    "apply_manifests",
    "create_resources",
    "label_node",
    "taint_node",
    "K8sClientError",
    "load_practice_kube_config",
]
