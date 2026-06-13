import time
from typing import List, Dict, Any, Tuple
from kubernetes import client, config
from kubernetes.client.rest import ApiException

def run_checks(checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Run a list of declarative checks against the local Kubernetes cluster.
    Returns a list of results: [{"passed": bool, "message": str, "name": str}, ...]
    """
    results = []
    try:
        config.load_kube_config()
    except Exception as e:
        return [{"passed": False, "message": f"Failed to load kubeconfig: {e}", "name": "Cluster Connection"}]

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    networking_v1 = client.NetworkingV1Api()
    
    for check in checks:
        check_type = check.get("type")
        fail_message = check.get("failMessage", f"Check {check_type} failed.")
        check_name = check.get("name", check_type)
        if "description" in check:
            check_name = check["description"]
        
        try:
            passed, err = _run_single_check(core_v1, apps_v1, networking_v1, check)
            results.append({
                "passed": passed,
                "message": "" if passed else (err or fail_message),
                "name": check_name
            })
        except ApiException as e:
            # If it's a 404, it means the resource doesn't exist, which usually means failure.
            if e.status == 404:
                results.append({"passed": False, "message": fail_message, "name": check_name})
            else:
                # For 401 or 500, it's an unexpected API error
                results.append({"passed": False, "message": f"Unexpected API Error: {e.reason}", "name": check_name})
        except Exception as e:
            results.append({"passed": False, "message": f"Internal Verification Error: {str(e)}", "name": check_name})
            
    return results

def _run_single_check(core_v1: client.CoreV1Api, apps_v1: client.AppsV1Api, net_v1: client.NetworkingV1Api, check: Dict[str, Any]) -> Tuple[bool, str]:
    check_type = check.get("type")
    
    # ─── CORE V1 ───
    if check_type == "namespace_exists":
        name = check.get("name")
        if not name: return False, "Invalid check: missing 'name'"
        core_v1.read_namespace(name=name)
        return True, ""
        
    elif check_type == "pod_running":
        name = check.get("name")
        namespace = check.get("namespace", "default")
        image = check.get("image")
        if not name: return False, "Invalid check: missing 'name'"
        pod = core_v1.read_namespaced_pod(name=name, namespace=namespace)
        if pod.status.phase != "Running": return False, ""
        if image:
            has_image = any(container.image == image for container in pod.spec.containers)
            if not has_image: return False, ""
        return True, ""
        
    elif check_type == "service_exists":
        name = check.get("name")
        namespace = check.get("namespace", "default")
        if not name: return False, "missing 'name'"
        core_v1.read_namespaced_service(name=name, namespace=namespace)
        return True, ""

    elif check_type == "configmap_exists":
        name = check.get("name")
        namespace = check.get("namespace", "default")
        if not name: return False, "missing 'name'"
        core_v1.read_namespaced_config_map(name=name, namespace=namespace)
        return True, ""

    # ─── APPS V1 ───
    elif check_type == "deployment_exists":
        name = check.get("name")
        namespace = check.get("namespace", "default")
        replicas = check.get("replicas")
        if not name: return False, "missing 'name'"
        dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        if replicas is not None:
            if dep.spec.replicas != replicas:
                return False, f"Expected {replicas} replicas, found {dep.spec.replicas}"
        return True, ""

    elif check_type == "daemonset_exists":
        name = check.get("name")
        namespace = check.get("namespace", "default")
        if not name: return False, "missing 'name'"
        apps_v1.read_namespaced_daemon_set(name=name, namespace=namespace)
        return True, ""

    # ─── FALLBACK ───
    elif check_type == "mock_check":
        # Always returns true for mock questions
        return True, ""

    else:
        return False, f"Unknown check type: {check_type}"
