"""Cluster context and safety guards for practice-cluster targeting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from kubernetes import config

from .. import config as cli_config


class ClusterTargetingError(Exception):
    """Raised when the CLI cannot confirm it is targeting the practice cluster."""


def get_container_name(cluster_name: str, role: str) -> str:
    """Return the full Docker container name for a KIND node role.

    KIND names containers as ``<cluster-name>-control-plane`` and
    ``<cluster-name>-worker`` (``worker2``, ``worker3``, ...).
    """
    if role == "control-plane":
        return f"{cluster_name}-control-plane"
    return f"{cluster_name}-{role}"


def get_kubeconfig_path() -> Path:
    """Return the path to the practice-cluster kubeconfig."""
    return cli_config.KUBECONFIG_PATH


def load_practice_kube_config() -> None:
    """Load the practice kubeconfig into the Kubernetes SDK.

    Raises ClusterTargetingError if the file is missing.
    """
    path = get_kubeconfig_path()
    if not path.exists():
        raise ClusterTargetingError(
            f"Practice kubeconfig not found: {path}. "
            "Start a question first with 'aicademy question start <id>'."
        )
    config.load_kube_config(config_file=str(path))


def _current_context_cluster(kubeconfig_path: Path) -> str | None:
    """Return the cluster name of the current context in the kubeconfig."""
    try:
        data = yaml.safe_load(kubeconfig_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    current = data.get("current-context")
    if not current:
        return None
    contexts = {c.get("name"): c for c in data.get("contexts", []) if isinstance(c, dict)}
    ctx = contexts.get(current)
    if not ctx:
        return None
    cluster_name = ctx.get("context", {}).get("cluster")
    clusters = {c.get("name"): c for c in data.get("clusters", []) if isinstance(c, dict)}
    cluster = clusters.get(cluster_name)
    if not cluster:
        return None
    return str(cluster_name)


def require_practice_cluster(cluster_name: str) -> None:
    """Abort if the active kubeconfig does not target the expected practice cluster."""
    path = get_kubeconfig_path()
    if not path.exists():
        raise ClusterTargetingError(
            f"Practice kubeconfig missing: {path}. "
            f"Run 'aicademy question start {cluster_name}' first."
        )
    actual = _current_context_cluster(path)
    # KIND names exported contexts/clusters with a 'kind-' prefix.
    allowed = {cluster_name, f"kind-{cluster_name}"}
    if actual not in allowed:
        raise ClusterTargetingError(
            f"Kubeconfig context mismatch: expected {cluster_name} "
            f"(or kind-{cluster_name}), got {actual}. "
            "Refusing to operate on a non-practice cluster."
        )


def get_active_session_cluster() -> str | None:
    """Return the cluster name stored in the active session, if any."""
    session = cli_config.get_active_session()
    if not session:
        return None
    return session.get("clusterName")


def build_session_context() -> dict[str, Any]:
    """Return a dict with session cluster targeting info."""
    session = cli_config.get_active_session() or {}
    return {
        "clusterName": session.get("clusterName"),
        "kubeconfig": str(get_kubeconfig_path()),
        "questionId": session.get("questionId"),
        "sessionId": session.get("sessionId"),
    }
