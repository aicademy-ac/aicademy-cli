from __future__ import annotations

from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from .. import config as cli_config


def run_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Run a list of declarative checks against the local Kubernetes cluster.
    Returns a list of results: [{"passed": bool, "message": str, "name": str}, ...]
    """
    results = []
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

    apis = {
        "core": core_v1,
        "apps": apps_v1,
        "net": networking_v1,
        "rbac": rbac_v1,
        "batch": batch_v1,
        "storage": storage_v1,
        "policy": policy_v1,
    }

    for check in checks:
        check_type = check.get("type")
        fail_message = check.get("failMessage", f"Check {check_type} failed.")
        check_name = check.get("name", check_type)
        if "description" in check:
            check_name = check["description"]

        try:
            passed, err = _run_single_check(apis, check)
            results.append(
                {
                    "passed": passed,
                    "message": "" if passed else (err or fail_message),
                    "name": check_name,
                }
            )
        except ApiException as e:
            # If it's a 404, it means the resource doesn't exist, which usually means failure.
            if e.status == 404:
                results.append({"passed": False, "message": fail_message, "name": check_name})
            else:
                # For 401 or 500, it's an unexpected API error
                results.append(
                    {
                        "passed": False,
                        "message": f"Unexpected API Error: {e.reason}",
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


def _run_single_check(apis: dict[str, Any], check: dict[str, Any]) -> tuple[bool, str]:
    check_type = check.get("type")
    name = check.get("name")
    namespace = check.get("namespace", "default")

    if check_type == "mock_check":
        return True, ""

    if not name and check_type not in ["node_labeled"]:
        return False, "missing 'name'"

    try:
        # CORE V1
        if check_type == "namespace_exists":
            apis["core"].read_namespace(name=name)
        elif check_type == "pod_running":
            pod = apis["core"].read_namespaced_pod(name=name, namespace=namespace)
            if pod.status.phase != "Running":
                return False, f"Pod is {pod.status.phase}"
            image = check.get("image")
            if image and not any(c.image == image for c in pod.spec.containers):
                return False, f"Image {image} not found in pod"
        elif check_type == "service_exists":
            apis["core"].read_namespaced_service(name=name, namespace=namespace)
        elif check_type == "configmap_exists":
            apis["core"].read_namespaced_config_map(name=name, namespace=namespace)
        elif check_type == "secret_exists":
            apis["core"].read_namespaced_secret(name=name, namespace=namespace)
        elif check_type == "pvc_exists":
            apis["core"].read_namespaced_persistent_volume_claim(name=name, namespace=namespace)
        elif check_type == "pv_exists":
            apis["core"].read_persistent_volume(name=name)
        elif check_type == "serviceaccount_exists":
            apis["core"].read_namespaced_service_account(name=name, namespace=namespace)
        elif check_type == "node_labeled":
            nodes = apis["core"].list_node().items
            label_key = check.get("label_key")
            label_value = check.get("label_value")
            found = any(n.metadata.labels.get(label_key) == label_value for n in nodes)
            if not found:
                return False, f"No node with label {label_key}={label_value}"

        # APPS V1
        elif check_type == "deployment_exists":
            dep = apis["apps"].read_namespaced_deployment(name=name, namespace=namespace)
            replicas = check.get("replicas")
            if replicas is not None and dep.spec.replicas != replicas:
                return False, f"Expected {replicas} replicas, found {dep.spec.replicas}"
        elif check_type == "daemonset_exists":
            apis["apps"].read_namespaced_daemon_set(name=name, namespace=namespace)
        elif check_type == "statefulset_exists":
            apis["apps"].read_namespaced_stateful_set(name=name, namespace=namespace)

        # NETWORKING V1
        elif check_type == "networkpolicy_exists":
            apis["net"].read_namespaced_network_policy(name=name, namespace=namespace)
        elif check_type == "ingress_exists":
            apis["net"].read_namespaced_ingress(name=name, namespace=namespace)

        # RBAC V1
        elif check_type == "role_exists":
            apis["rbac"].read_namespaced_role(name=name, namespace=namespace)
        elif check_type == "rolebinding_exists":
            apis["rbac"].read_namespaced_role_binding(name=name, namespace=namespace)
        elif check_type == "clusterrole_exists":
            apis["rbac"].read_cluster_role(name=name)
        elif check_type == "clusterrolebinding_exists":
            apis["rbac"].read_cluster_role_binding(name=name)

        # BATCH V1
        elif check_type == "job_exists":
            apis["batch"].read_namespaced_job(name=name, namespace=namespace)
        elif check_type == "cronjob_exists":
            apis["batch"].read_namespaced_cron_job(name=name, namespace=namespace)

        # STORAGE V1
        elif check_type == "storageclass_exists":
            apis["storage"].read_storage_class(name=name)

        # POLICY V1
        elif check_type == "pdb_exists":
            apis["policy"].read_namespaced_pod_disruption_budget(name=name, namespace=namespace)

        elif check_type == "bash_check":
            command = check.get("command")
            if not command:
                return False, "Missing bash command"
            import subprocess
            import os

            env = os.environ.copy()
            env["KUBECONFIG"] = str(cli_config.KUBECONFIG_PATH)
            
            try:
                res = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                return False, "Command timed out after 30 seconds"

            if res.returncode != 0:
                return False, f"Command failed: {res.stderr}"
        else:
            return False, f"Unknown check type: {check_type}"

        return True, ""
    except ApiException as e:
        if e.status == 404:
            return False, "Resource not found"
        raise e
