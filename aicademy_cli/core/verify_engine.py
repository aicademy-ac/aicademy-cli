"""Declarative verification engine."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .. import config as cli_config
from .cluster_context import ClusterTargetingError, require_practice_cluster
from .docker_client import DockerClient, DockerClientError


class VerifyEngineError(Exception):
    """Raised when the verification engine encounters a fatal error."""


CheckHandler = Callable[[dict[str, Any], "CheckContext"], tuple[bool, str]]
_CHECK_REGISTRY: dict[str, CheckHandler] = {}

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
    "openssl",
}
_BLOCKED_BINARIES = {"sh", "bash", "/bin/sh", "/bin/bash", "cmd", "powershell"}


class CheckContext:
    """Runtime context passed to every check handler."""

    def __init__(
        self,
        apis: dict[str, Any],
        docker_client: DockerClient | None,
        cluster_name: str | None,
    ) -> None:
        self.apis = apis
        self.docker_client = docker_client
        self.cluster_name = cluster_name


def register_check(type_: str) -> Callable[[CheckHandler], CheckHandler]:
    """Decorator that registers a handler for a VerifyCheck type."""

    def decorator(fn: CheckHandler) -> CheckHandler:
        _CHECK_REGISTRY[type_] = fn
        return fn

    return decorator


def _assert_allowed_binary(binary: str) -> None:
    if binary in _BLOCKED_BINARIES:
        raise VerifyEngineError(
            f"Shell interpreter '{binary}' is not allowed in declarative checks."
        )
    if binary not in _ALLOWED_BINARIES:
        raise VerifyEngineError(
            f"Binary '{binary}' is not in the allowed list for declarative checks."
        )


def _jsonpath_value(obj: Any, path: str) -> Any:
    """Very small JSONPath-like resolver for simple dotted paths."""
    parts = [p for p in path.replace("[", ".").replace("]", "").split(".") if p]
    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def run_checks(
    checks: list[dict[str, Any]],
    cluster_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Run a list of declarative checks against the practice Kubernetes cluster.
    Returns a list of results: [{"passed": bool, "message": str, "name": str}, ...]
    """
    if not cluster_name:
        return [
            {
                "passed": False,
                "message": "No active practice session cluster name provided.",
                "name": "Cluster Connection",
            }
        ]

    try:
        require_practice_cluster(cluster_name)
    except ClusterTargetingError as e:
        return [
            {
                "passed": False,
                "message": f"Practice cluster targeting check failed: {e}",
                "name": "Cluster Connection",
            }
        ]

    try:
        config.load_kube_config(config_file=str(cli_config.KUBECONFIG_PATH))
    except Exception as e:
        return [
            {
                "passed": False,
                "message": f"Failed to load kubeconfig: {e}",
                "name": "Cluster Connection",
            }
        ]

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    networking_v1 = client.NetworkingV1Api()
    rbac_v1 = client.RbacAuthorizationV1Api()
    batch_v1 = client.BatchV1Api()
    storage_v1 = client.StorageV1Api()
    policy_v1 = client.PolicyV1Api()
    autoscaling_v2 = client.AutoscalingV2Api()
    scheduling_v1 = client.SchedulingV1Api()
    apiextensions_v1 = client.ApiextensionsV1Api()

    apis = {
        "core": core_v1,
        "apps": apps_v1,
        "net": networking_v1,
        "rbac": rbac_v1,
        "batch": batch_v1,
        "storage": storage_v1,
        "policy": policy_v1,
        "autoscaling": autoscaling_v2,
        "scheduling": scheduling_v1,
        "apiextensions": apiextensions_v1,
    }

    ctx = CheckContext(apis, None, cluster_name)
    results = []

    for check in checks:
        check_type = check.get("type", "")
        fail_message = check.get("failMessage", f"Check {check_type} failed.")
        check_name = check.get("description") or check.get("name") or check_type

        handler = _CHECK_REGISTRY.get(check_type)
        if handler is None:
            results.append(
                {
                    "passed": False,
                    "message": f"Unknown check type: {check_type}",
                    "name": check_name,
                }
            )
            continue

        try:
            passed, err = handler(check, ctx)
            results.append(
                {
                    "passed": passed,
                    "message": "" if passed else (err or fail_message),
                    "name": check_name,
                }
            )
        except ApiException as e:
            if e.status == 404:
                results.append({"passed": False, "message": fail_message, "name": check_name})
            else:
                results.append(
                    {
                        "passed": False,
                        "message": f"Unexpected API Error: {e.reason}",
                        "name": check_name,
                    }
                )
        except (DockerClientError, ClusterTargetingError) as e:
            results.append(
                {
                    "passed": False,
                    "message": f"Cluster targeting error: {e}",
                    "name": check_name,
                }
            )
        except Exception as e:
            results.append(
                {
                    "passed": False,
                    "message": f"Internal Verification Error: {str(e)}",
                    "name": check_name,
                }
            )

    return results


# ─── Generic existence-check factory ──────────────────────────────────────────

ExistenceMethod = Callable[..., Any]
EXISTENCE_CHECKS: dict[str, tuple[str, ExistenceMethod]] = {
    "namespace_exists": ("core", client.CoreV1Api.read_namespace),
    "configmap_exists": ("core", client.CoreV1Api.read_namespaced_config_map),
    "secret_exists": ("core", client.CoreV1Api.read_namespaced_secret),
    "serviceaccount_exists": ("core", client.CoreV1Api.read_namespaced_service_account),
    "pv_exists": ("core", client.CoreV1Api.read_persistent_volume),
    "pvc_exists": ("core", client.CoreV1Api.read_namespaced_persistent_volume_claim),
    "service_exists": ("core", client.CoreV1Api.read_namespaced_service),
    "deployment_exists": ("apps", client.AppsV1Api.read_namespaced_deployment),
    "daemonset_exists": ("apps", client.AppsV1Api.read_namespaced_daemon_set),
    "statefulset_exists": ("apps", client.AppsV1Api.read_namespaced_stateful_set),
    "networkpolicy_exists": ("net", client.NetworkingV1Api.read_namespaced_network_policy),
    "ingress_exists": ("net", client.NetworkingV1Api.read_namespaced_ingress),
    "role_exists": ("rbac", client.RbacAuthorizationV1Api.read_namespaced_role),
    "rolebinding_exists": ("rbac", client.RbacAuthorizationV1Api.read_namespaced_role_binding),
    "clusterrole_exists": ("rbac", client.RbacAuthorizationV1Api.read_cluster_role),
    "clusterrolebinding_exists": (
        "rbac",
        client.RbacAuthorizationV1Api.read_cluster_role_binding,
    ),
    "job_exists": ("batch", client.BatchV1Api.read_namespaced_job),
    "cronjob_exists": ("batch", client.BatchV1Api.read_namespaced_cron_job),
    "storageclass_exists": ("storage", client.StorageV1Api.read_storage_class),
    "pdb_exists": ("policy", client.PolicyV1Api.read_namespaced_pod_disruption_budget),
    "hpa_exists": ("autoscaling", client.AutoscalingV2Api.read_namespaced_horizontal_pod_autoscaler),
    "priorityclass_exists": ("scheduling", client.SchedulingV1Api.read_priority_class),
    "crd_exists": ("apiextensions", client.ApiextensionsV1Api.read_custom_resource_definition),
}


def _make_exists_handler(api_key: str, method: ExistenceMethod) -> CheckHandler:
    def handler(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
        kwargs: dict[str, Any] = {"name": check.get("name")}
        namespace = check.get("namespace")
        if namespace is not None:
            kwargs["namespace"] = namespace
        method(ctx.apis[api_key], **kwargs)
        return True, ""

    return handler


for _check_type, (_api_key, _method) in EXISTENCE_CHECKS.items():
    register_check(_check_type)(_make_exists_handler(_api_key, _method))


# ─── Specific check handlers ──────────────────────────────────────────────────


@register_check("pod_running")
def _check_pod_running(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    pod = ctx.apis["core"].read_namespaced_pod(name=name, namespace=namespace)
    if pod.status.phase != "Running":
        return False, f"Pod {name} is {pod.status.phase}"
    expected_image = check.get("image")
    if expected_image:
        containers = pod.spec.containers or []
        found = any(expected_image in (c.image or "") for c in containers)
        if not found:
            return False, f"Pod {name} does not use image {expected_image}"
    return True, ""


@register_check("deployment_exists")
def _check_deployment_exists(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    dep = ctx.apis["apps"].read_namespaced_deployment(name=name, namespace=namespace)
    replicas = check.get("replicas")
    if replicas is not None and dep.spec.replicas != replicas:
        return False, f"Expected {replicas} replicas, found {dep.spec.replicas}"
    expected_image = check.get("image")
    if expected_image:
        containers = dep.spec.template.spec.containers or []
        found = any(expected_image in (c.image or "") for c in containers)
        if not found:
            return False, f"Deployment {name} does not use image {expected_image}"
    return True, ""


@register_check("deployment_image")
def _check_deployment_image(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    dep = ctx.apis["apps"].read_namespaced_deployment(name=name, namespace=namespace)
    expected = check.get("image", "")
    container_name = check.get("containerName")
    containers = dep.spec.template.spec.containers or []
    if container_name:
        containers = [c for c in containers if c.name == container_name]
    if not containers:
        return False, f"Container {container_name or ''} not found in deployment {name}"
    found = any(expected in (c.image or "") for c in containers)
    if not found:
        return False, f"Expected image containing {expected}"
    return True, ""


@register_check("service_type")
def _check_service_type(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    svc = ctx.apis["core"].read_namespaced_service(name=name, namespace=namespace)
    expected = check.get("serviceType")
    if svc.spec.type != expected:
        return False, f"Expected service type {expected}, got {svc.spec.type}"
    return True, ""


@register_check("service_nodeport")
def _check_service_nodeport(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    svc = ctx.apis["core"].read_namespaced_service(name=name, namespace=namespace)
    expected_port = check.get("port")
    expected_node_port = check.get("nodePort")
    found = False
    for p in svc.spec.ports or []:
        if expected_port is not None and p.port != expected_port:
            continue
        if p.node_port == expected_node_port:
            found = True
            break
    if not found:
        return False, f"NodePort {expected_node_port} not found on service {name}"
    return True, ""


@register_check("node_label")
def _check_node_label(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    nodes = ctx.apis["core"].list_node().items
    label_key = check.get("label_key")
    label_value = check.get("label_value")
    found = any(n.metadata.labels.get(label_key) == label_value for n in nodes)
    if not found:
        return False, f"No node with label {label_key}={label_value}"
    return True, ""


@register_check("node_ready")
def _check_node_ready(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    label_selector = check.get("labelSelector")
    
    nodes_to_check = []
    if name:
        nodes_to_check.append(ctx.apis["core"].read_node(name=name))
    elif label_selector:
        nodes = ctx.apis["core"].list_node(label_selector=label_selector).items
        if not nodes:
            return False, f"No nodes found matching selector: {label_selector}"
        nodes_to_check.extend(nodes)
    else:
        return False, "Either 'name' or 'labelSelector' must be provided for node_ready check"
        
    for node in nodes_to_check:
        ready = any(
            c.type == "Ready" and c.status == "True" for c in (node.status.conditions or [])
        )
        if not ready:
            return False, f"Node {node.metadata.name} is not Ready"
    return True, ""


@register_check("node_version")
def _check_node_version(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    node = ctx.apis["core"].read_node(name=name)
    version = node.status.node_info.kubelet_version or ""
    expected = check.get("version", "")
    if expected not in version:
        return False, f"Node {name} version {version} does not contain {expected}"
    return True, ""


@register_check("pod_env")
def _check_pod_env(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    pod = ctx.apis["core"].read_namespaced_pod(name=name, namespace=namespace)
    expected = check.get("env", {})
    containers = pod.spec.containers or []
    for container in containers:
        env_map = {e.name: e.value for e in (container.env or [])}
        for key, value in expected.items():
            if env_map.get(key) != value:
                return False, f"Container {container.name} env {key} != {value}"
    return True, ""


@register_check("pod_field")
def _check_pod_field(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    name = check.get("name")
    namespace = check.get("namespace", "default")
    pod = ctx.apis["core"].read_namespaced_pod(name=name, namespace=namespace)
    actual = _jsonpath_value(pod.to_dict(), check.get("jsonPath", ""))
    expected = check.get("expected", "")
    if str(actual) != str(expected):
        return False, f"Expected {check['jsonPath']}={expected}, got {actual}"
    return True, ""


@register_check("resource_field")
def _check_resource_field(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    obj = _read_generic_resource(
        ctx.apis, check.get("kind", ""), check.get("name", ""), check.get("namespace", "")
    )
    actual = _jsonpath_value(obj.to_dict(), check.get("jsonPath", ""))
    expected = check.get("expected", "")
    if str(actual) != str(expected):
        return False, f"Expected {check['jsonPath']}={expected}, got {actual}"
    return True, ""


@register_check("container_exec")
def _check_container_exec(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    if ctx.cluster_name is None:
        return False, "No active practice session cluster name provided"
    command = check.get("command", [])
    if not isinstance(command, list) or not all(isinstance(c, str) for c in command):
        return False, "container_exec requires command as a list of strings"
    _assert_allowed_binary(command[0])
    if ctx.docker_client is None:
        ctx.docker_client = DockerClient()
    container_role = check.get("container", "control-plane")
    try:
        result = ctx.docker_client.exec(ctx.cluster_name, container_role, command)
    except (DockerClientError, ClusterTargetingError) as exc:
        return False, str(exc)
    exit_code = result.exit_code
    stdout, stderr = result.output
    stdout_text = (stdout or b"").decode("utf-8", errors="replace")
    stderr_text = (stderr or b"").decode("utf-8", errors="replace")
    output = stdout_text + stderr_text

    expected_exit = check.get("expectedExitCode")
    if expected_exit is None:
        expected_exit = 0
    if exit_code != expected_exit:
        return False, f"Expected exit {expected_exit}, got {exit_code}: {output}"

    expected_output = check.get("expectedOutput")
    if expected_output is not None and expected_output not in output:
        return False, f"Expected output {expected_output} not found"
    for fragment in (check.get("outputContains") or []):
        if fragment not in output:
            return False, f"Missing output fragment: {fragment}"
    for fragment in (check.get("outputNotContains") or []):
        if fragment in output:
            return False, f"Unexpected output fragment: {fragment}"
    return True, ""


def _read_generic_resource(
    apis: dict[str, Any], kind: str, name: str, namespace: str
) -> Any:
    kind = kind.lower()
    if kind == "deployment":
        return apis["apps"].read_namespaced_deployment(name=name, namespace=namespace)
    if kind == "daemonset":
        return apis["apps"].read_namespaced_daemon_set(name=name, namespace=namespace)
    if kind == "statefulset":
        return apis["apps"].read_namespaced_stateful_set(name=name, namespace=namespace)
    if kind == "pod":
        return apis["core"].read_namespaced_pod(name=name, namespace=namespace)
    if kind == "service":
        return apis["core"].read_namespaced_service(name=name, namespace=namespace)
    if kind == "configmap":
        return apis["core"].read_namespaced_config_map(name=name, namespace=namespace)
    if kind == "secret":
        return apis["core"].read_namespaced_secret(name=name, namespace=namespace)
    if kind == "job":
        return apis["batch"].read_namespaced_job(name=name, namespace=namespace)
    if kind == "cronjob":
        return apis["batch"].read_namespaced_cron_job(name=name, namespace=namespace)
    if kind == "networkpolicy":
        return apis["net"].read_namespaced_network_policy(name=name, namespace=namespace)
    if kind == "ingress":
        return apis["net"].read_namespaced_ingress(name=name, namespace=namespace)
    if kind == "role":
        return apis["rbac"].read_namespaced_role(name=name, namespace=namespace)
    if kind == "rolebinding":
        return apis["rbac"].read_namespaced_role_binding(name=name, namespace=namespace)
    if kind == "clusterrole":
        return apis["rbac"].read_cluster_role(name=name)
    if kind == "clusterrolebinding":
        return apis["rbac"].read_cluster_role_binding(name=name)
    if kind == "storageclass":
        return apis["storage"].read_storage_class(name=name)
    if kind == "poddisruptionbudget":
        return apis["policy"].read_namespaced_pod_disruption_budget(name=name, namespace=namespace)
    if kind == "hpa" or kind == "horizontalpodautoscaler":
        return apis["autoscaling"].read_namespaced_horizontal_pod_autoscaler(name=name, namespace=namespace)
    if kind == "priorityclass":
        return apis["scheduling"].read_priority_class(name=name)
    if kind == "crd" or kind == "customresourcedefinition":
        return apis["apiextensions"].read_custom_resource_definition(name=name)
    raise ValueError(f"Unsupported generic resource kind: {kind}")


@register_check("resource_exists")
def _check_resource_exists(check: dict[str, Any], ctx: CheckContext) -> tuple[bool, str]:
    kind = check.get("kind", "")
    _read_generic_resource(ctx.apis, kind, check.get("name", ""), check.get("namespace", ""))
    return True, ""


__all__ = ["run_checks", "register_check", "VerifyEngineError", "CheckContext"]
