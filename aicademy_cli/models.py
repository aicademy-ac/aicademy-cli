"""Pydantic models for the Aicademy API contract."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Literal, Union

from pydantic import BaseModel, field_validator
from typing_extensions import TypeAlias

SHELL_PATTERNS = ("sh -c", "bash -c", "/bin/sh", "/bin/bash")
SHELL_METACHARACTERS = ("|", "&&", "||", ";", "`", "$(")
HARDCODED_NODE_PATTERNS = ("kind-control-plane", "kind-worker", "aicademy-")

Role = Literal["control-plane", "worker", "worker2", "worker3"]

# Allowed absolute paths for ConfigFileAction inside KIND node containers.
# These are system/service directories that practice scenarios legitimately modify.
_ALLOWED_CONFIG_PATH_PREFIXES = (
    "/etc/kubernetes/",
    "/etc/containerd/",
    "/etc/cni/",
    "/etc/sysctl.d/",
    "/etc/systemd/",
    "/etc/ssl/certs/",
    "/etc/pki/",
    "/usr/local/bin/",
    "/opt/",
    "/var/lib/kubelet/",
)

_VALID_CLUSTER_TEMPLATES = {"1-node", "2-node", "3-node"}


def _assert_safe_command(command: list[str]) -> list[str]:
    joined = " ".join(command)
    if any(p in joined for p in SHELL_PATTERNS):
        raise ValueError(f"Shell strings are not allowed in command: {command}")
    if any(p in joined for p in SHELL_METACHARACTERS):
        raise ValueError(f"Shell metacharacters are not allowed in command: {command}")
    if any(p in joined for p in HARDCODED_NODE_PATTERNS):
        raise ValueError(f"Hardcoded node names are not allowed in command: {command}")
    return command


class K8sApplyAction(BaseModel):
    type: Literal["k8s_apply"]
    manifests: list[str]


class K8sCreateAction(BaseModel):
    type: Literal["k8s_create"]
    resources: list[dict[str, Any]]


class DockerExecAction(BaseModel):
    type: Literal["docker_exec"]
    container: Role
    command: list[str]
    description: str | None = None
    privileged: bool = False
    user: str = ""
    environment: dict[str, str] | None = None

    @field_validator("command", mode="after")
    @classmethod
    def no_shell(cls, v: list[str]) -> list[str]:
        return _assert_safe_command(v)


class ContainerStopAction(BaseModel):
    type: Literal["container_stop"]
    container: Role


class ContainerStartAction(BaseModel):
    type: Literal["container_start"]
    container: Role


class ContainerRestartAction(BaseModel):
    type: Literal["container_restart"]
    container: Role


class NodeLabelAction(BaseModel):
    type: Literal["node_label"]
    node: str
    labels: dict[str, str]


class NodeTaintAction(BaseModel):
    type: Literal["node_taint"]
    node: str
    taints: list[dict[str, Any]]


class ConfigFileAction(BaseModel):
    type: Literal["config_file"]
    container: Role
    path: str
    content: str
    mode: str | None = None

    @field_validator("path", mode="after")
    @classmethod
    def safe_config_path(cls, v: str) -> str:
        normalized = re.sub(r"/+", "/", v.strip())
        if not normalized.startswith("/"):
            raise ValueError(f"Config file path must be absolute: {v!r}")
        if ".." in PurePosixPath(normalized).parts:
            raise ValueError(f"Config file path must not contain '..' traversal: {v!r}")
        if not any(normalized.startswith(prefix) for prefix in _ALLOWED_CONFIG_PATH_PREFIXES):
            raise ValueError(f"Config file path is not in an allowed directory: {v!r}")
        return normalized


class ServiceAction(BaseModel):
    type: Literal["service_action"]
    container: Role
    service: str
    action: Literal["stop", "start", "restart", "status"]


ClusterAction: TypeAlias = Union[
    K8sApplyAction,
    K8sCreateAction,
    DockerExecAction,
    ContainerStopAction,
    ContainerStartAction,
    ContainerRestartAction,
    NodeLabelAction,
    NodeTaintAction,
    ConfigFileAction,
    ServiceAction,
]


class ClusterState(BaseModel):
    actions: list[ClusterAction]


class BaseCheck(BaseModel):
    name: str | None = None
    namespace: str | None = None
    failMessage: str
    description: str | None = None


class ResourceExistsCheck(BaseCheck):
    type: Literal["resource_exists"]
    kind: str


class PodRunningCheck(BaseCheck):
    type: Literal["pod_running"]
    image: str | None = None


class DeploymentExistsCheck(BaseCheck):
    type: Literal["deployment_exists"]
    replicas: int | None = None
    image: str | None = None


class DeploymentImageCheck(BaseCheck):
    type: Literal["deployment_image"]
    image: str
    containerName: str | None = None


class PodEnvCheck(BaseCheck):
    type: Literal["pod_env"]
    env: dict[str, str]


class PodFieldCheck(BaseCheck):
    type: Literal["pod_field"]
    jsonPath: str
    expected: str


class ResourceFieldCheck(BaseCheck):
    type: Literal["resource_field"]
    kind: str
    jsonPath: str
    expected: str


class ServiceExistsCheck(BaseCheck):
    type: Literal["service_exists"]


class ServiceTypeCheck(BaseCheck):
    type: Literal["service_type"]
    serviceType: str


class ServiceNodePortCheck(BaseCheck):
    type: Literal["service_nodeport"]
    nodePort: int
    port: int | None = None


class SecretExistsCheck(BaseCheck):
    type: Literal["secret_exists"]


class ConfigMapExistsCheck(BaseCheck):
    type: Literal["configmap_exists"]


class NamespaceExistsCheck(BaseCheck):
    type: Literal["namespace_exists"]


class NodeLabelCheck(BaseCheck):
    type: Literal["node_label", "node_labeled"]
    label_key: str
    label_value: str


class NodeReadyCheck(BaseCheck):
    type: Literal["node_ready"]


class NodeVersionCheck(BaseCheck):
    type: Literal["node_version"]
    version: str


class ContainerExecCheck(BaseCheck):
    type: Literal["container_exec"]
    container: Role
    command: list[str]
    expectedExitCode: int | None = None
    expectedOutput: str | None = None
    outputContains: list[str] | None = None
    outputNotContains: list[str] | None = None

    @field_validator("command", mode="after")
    @classmethod
    def no_shell(cls, v: list[str]) -> list[str]:
        return _assert_safe_command(v)


class DaemonSetExistsCheck(BaseCheck):
    type: Literal["daemonset_exists"]


class StatefulSetExistsCheck(BaseCheck):
    type: Literal["statefulset_exists"]
    replicas: int | None = None


class JobExistsCheck(BaseCheck):
    type: Literal["job_exists"]


class CronJobExistsCheck(BaseCheck):
    type: Literal["cronjob_exists"]


class NetworkPolicyExistsCheck(BaseCheck):
    type: Literal["networkpolicy_exists"]


class IngressExistsCheck(BaseCheck):
    type: Literal["ingress_exists"]


class RoleExistsCheck(BaseCheck):
    type: Literal["role_exists"]


class RoleBindingExistsCheck(BaseCheck):
    type: Literal["rolebinding_exists"]


class ClusterRoleExistsCheck(BaseCheck):
    type: Literal["clusterrole_exists"]


class ClusterRoleBindingExistsCheck(BaseCheck):
    type: Literal["clusterrolebinding_exists"]


class StorageClassExistsCheck(BaseCheck):
    type: Literal["storageclass_exists"]


class PodDisruptionBudgetExistsCheck(BaseCheck):
    type: Literal["pdb_exists"]


class ServiceActionCheck(BaseCheck):
    type: Literal["service_action"]
    container: Role
    service: str


class PvExistsCheck(BaseCheck):
    type: Literal["pv_exists"]


class PvcExistsCheck(BaseCheck):
    type: Literal["pvc_exists"]


class ServiceAccountExistsCheck(BaseCheck):
    type: Literal["serviceaccount_exists"]


VerifyCheck: TypeAlias = Union[
    ResourceExistsCheck,
    PodRunningCheck,
    DeploymentExistsCheck,
    DeploymentImageCheck,
    PodEnvCheck,
    PodFieldCheck,
    ResourceFieldCheck,
    ServiceExistsCheck,
    ServiceTypeCheck,
    ServiceNodePortCheck,
    SecretExistsCheck,
    ConfigMapExistsCheck,
    NamespaceExistsCheck,
    NodeLabelCheck,
    NodeReadyCheck,
    NodeVersionCheck,
    ContainerExecCheck,
    DaemonSetExistsCheck,
    StatefulSetExistsCheck,
    JobExistsCheck,
    CronJobExistsCheck,
    NetworkPolicyExistsCheck,
    IngressExistsCheck,
    RoleExistsCheck,
    RoleBindingExistsCheck,
    ClusterRoleExistsCheck,
    ClusterRoleBindingExistsCheck,
    StorageClassExistsCheck,
    PodDisruptionBudgetExistsCheck,
    ServiceActionCheck,
    PvExistsCheck,
    PvcExistsCheck,
    ServiceAccountExistsCheck,
]


class PracticeTask(BaseModel):
    title: str
    description: str
    hint: str | None = None


class PracticeQuestion(BaseModel):
    id: str
    category: Literal["cka", "ckad", "cks"]
    subCategory: str
    level: Literal["beginner", "intermediate", "advanced", "expert"]
    title: str
    description: str
    scenario: str
    tasks: list[PracticeTask]
    hints: list[str]
    tags: list[str]
    estimatedMinutes: int
    xp: int | None = None
    isFree: bool | None = None
    clusterTemplate: str | None = None
    minimumCliVersion: str | None = None
    clusterState: ClusterState | None = None
    breakers: list[ClusterAction] | None = None
    verifyChecks: list[VerifyCheck] | None = None

    @field_validator("clusterTemplate", mode="after")
    @classmethod
    def known_cluster_template(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in _VALID_CLUSTER_TEMPLATES:
            raise ValueError(
                f"Unknown cluster template {v!r}; must be one of {_VALID_CLUSTER_TEMPLATES}"
            )
        return v


class StartSessionResponse(BaseModel):
    sessionId: str
    question: PracticeQuestion
    verificationToken: str
    verificationSecret: str
    clusterName: str | None = None
    startedAt: str
    clusterState: ClusterState | None = None
    breakers: list[ClusterAction] | None = None
    minimumCliVersion: str | None = None
    kindConfigContent: str


class ActiveSessionResponse(BaseModel):
    session: dict[str, Any] | None
    question: PracticeQuestion | None


class QuestionDetailResponse(BaseModel):
    question: PracticeQuestion
    sessionId: str
    verifyChecks: list[VerifyCheck] | None = None
    clusterState: ClusterState | None = None
    breakers: list[ClusterAction] | None = None
    minimumCliVersion: str | None = None
    kindConfigContent: str
