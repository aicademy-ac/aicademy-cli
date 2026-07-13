"""Declarative cluster setup and breaker engine."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from rich.console import Console

from .cluster_context import ClusterTargetingError, require_practice_cluster
from .docker_client import DockerClient, DockerClientError
from .k8s_client import K8sClientError, apply_manifests, create_resources, label_node, taint_node
from .utils import escape_rich_markup

console = Console()


class ClusterSetupError(Exception):
    """Raised when a cluster setup or breaker action fails."""


ActionHandler = Callable[[str, dict[str, Any], Path], Awaitable[None]]
_ACTION_REGISTRY: dict[str, ActionHandler] = {}

CLUSTER_TEMPLATE_ROLES: dict[str, list[str]] = {
    "1-node": ["control-plane"],
    "2-node": ["control-plane", "worker"],
    "3-node": ["control-plane", "worker", "worker2"],
}


def _roles_for_template(template_name: str | None) -> list[str] | None:
    return CLUSTER_TEMPLATE_ROLES.get(template_name) if template_name else None

_ALLOWED_BINARIES = {
    "etcdctl",
    "systemctl",
    "test",
    "mkdir",
    "rm",
    "cat",
    "grep",
    "sed",
    "crictl",
    "ctr",
    "journalctl",
    "kubectl",
    "kubeadm",
}
_BLOCKED_BINARIES = {"sh", "bash", "/bin/sh", "/bin/bash", "cmd", "powershell"}


def register_action(type_: str) -> Callable[[ActionHandler], ActionHandler]:
    """Decorator that registers a handler for a ClusterAction type."""

    def decorator(fn: ActionHandler) -> ActionHandler:
        _ACTION_REGISTRY[type_] = fn
        return fn

    return decorator


def _assert_allowed_binary(binary: str) -> None:
    if binary in _BLOCKED_BINARIES:
        raise ClusterSetupError(
            f"Shell interpreter '{binary}' is not allowed in declarative actions."
        )
    if binary not in _ALLOWED_BINARIES:
        raise ClusterSetupError(
            f"Binary '{binary}' is not in the allowed list for declarative actions."
        )


def _docker_client() -> DockerClient:
    return DockerClient()


async def apply_cluster_state(
    cluster_name: str,
    state: dict[str, Any] | None,
    kubeconfig: Path,
    cluster_template: str | None = None,
) -> None:
    """Apply the declarative clusterState to the practice cluster."""
    if not state:
        return
    require_practice_cluster(cluster_name)
    actions = state.get("actions", [])
    if not actions:
        return
    allowed_roles = _roles_for_template(cluster_template)
    _validate_action_roles(actions, allowed_roles)
    console.print("\n[bold cyan]Applying cluster state...[/bold cyan]")
    for action in actions:
        await _apply_action(cluster_name, action, kubeconfig)


async def apply_breakers(
    cluster_name: str,
    breakers: list[dict[str, Any]] | None,
    kubeconfig: Path,
    cluster_template: str | None = None,
) -> None:
    """Apply declarative breaker/chaos actions to the practice cluster."""
    if not breakers:
        return
    require_practice_cluster(cluster_name)
    allowed_roles = _roles_for_template(cluster_template)
    _validate_action_roles(breakers, allowed_roles)
    console.print("\n[bold cyan]Injecting practice failures...[/bold cyan]")
    for breaker in breakers:
        await _apply_action(cluster_name, breaker, kubeconfig)


def _validate_action_roles(actions: list[dict[str, Any]], allowed_roles: list[str] | None) -> None:
    if allowed_roles is None:
        return
    for action in actions:
        container = action.get("container")
        if container and container not in allowed_roles:
            raise ClusterSetupError(
                f"Action references role '{container}' which is not available "
                f"in this cluster template (available: {', '.join(allowed_roles)})"
            )


async def _apply_action(cluster_name: str, action: dict[str, Any], kubeconfig: Path) -> None:
    action_type = action.get("type", "")
    if not isinstance(action_type, str):
        raise ClusterSetupError("Action type must be a string")
    description = action.get("description") or action_type
    console.print(f"  [dim]{escape_rich_markup(str(description))}[/dim]")

    handler = _ACTION_REGISTRY.get(action_type)
    if handler is None:
        raise ClusterSetupError(f"Unknown cluster action type: {action_type}")

    try:
        await handler(cluster_name, action, kubeconfig)
    except (ClusterTargetingError, DockerClientError, K8sClientError) as exc:
        raise ClusterSetupError(f"Setup action failed ({action_type}): {exc}") from exc


@register_action("k8s_apply")
async def _handle_k8s_apply(cluster_name: str, action: dict[str, Any], kubeconfig: Path) -> None:
    apply_manifests(kubeconfig, action.get("manifests", []))


@register_action("k8s_create")
async def _handle_k8s_create(cluster_name: str, action: dict[str, Any], kubeconfig: Path) -> None:
    create_resources(kubeconfig, action.get("resources", []))


@register_action("docker_exec")
async def _handle_docker_exec(cluster_name: str, action: dict[str, Any], kubeconfig: Path) -> None:
    command = action.get("command")
    if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
        raise ClusterSetupError("docker_exec action requires command as a list of strings")
    _assert_allowed_binary(command[0])
    result = _docker_client().exec(
        cluster_name,
        action["container"],
        command,
        privileged=action.get("privileged", False),
        user=action.get("user", ""),
        environment=action.get("environment"),
    )
    if result.exit_code != 0:
        stdout, stderr = result.output
        stdout_text = (stdout or b"").decode("utf-8", errors="replace")
        stderr_text = (stderr or b"").decode("utf-8", errors="replace")
        raise ClusterSetupError(
            f"docker_exec exited {result.exit_code}: {stdout_text}\n{stderr_text}"
        )


@register_action("container_stop")
async def _handle_container_stop(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    _docker_client().stop_container(cluster_name, action["container"])


@register_action("container_start")
async def _handle_container_start(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    _docker_client().start_container(cluster_name, action["container"])


@register_action("container_restart")
async def _handle_container_restart(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    _docker_client().restart_container(cluster_name, action["container"])


@register_action("node_label")
async def _handle_node_label(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    label_node(kubeconfig, action["node"], action["labels"])


@register_action("node_taint")
async def _handle_node_taint(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    taint_node(kubeconfig, action["node"], action["taints"])


@register_action("config_file")
async def _handle_config_file(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    _docker_client().put_file(
        cluster_name,
        action["container"],
        action["path"],
        action["content"],
        mode=action.get("mode", "644"),
    )


@register_action("service_action")
async def _handle_service_action(
    cluster_name: str, action: dict[str, Any], kubeconfig: Path
) -> None:
    service = action["service"]
    svc_action = action["action"]
    command = ["systemctl", svc_action, service]
    _assert_allowed_binary(command[0])
    result = _docker_client().exec(cluster_name, action["container"], command)
    if result.exit_code != 0 and svc_action != "status":
        stdout, stderr = result.output
        stdout_text = (stdout or b"").decode("utf-8", errors="replace")
        stderr_text = (stderr or b"").decode("utf-8", errors="replace")
        raise ClusterSetupError(
            f"service_action failed ({svc_action} {service}): {stdout_text}\n{stderr_text}"
        )


__all__ = ["apply_cluster_state", "apply_breakers", "ClusterSetupError", "register_action"]
