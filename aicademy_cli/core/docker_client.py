"""Docker SDK wrapper for KIND node operations."""

from __future__ import annotations

import io
import tarfile

import docker
import docker.errors
from docker.models.containers import Container, ExecResult

from .cluster_context import get_container_name


class DockerClientError(Exception):
    """Raised when a Docker operation fails."""


class DockerClient:
    """Thin wrapper around docker-py for operating on KIND nodes."""

    def __init__(self) -> None:
        self._client = docker.from_env()

    def _get_container(self, cluster_name: str, role: str) -> Container:
        """Return a Docker Container object for a KIND node role."""
        name = get_container_name(cluster_name, role)
        try:
            return self._client.containers.get(name)
        except docker.errors.NotFound as exc:
            raise DockerClientError(
                f"KIND container not found: {name}. Is the cluster running?"
            ) from exc

    def exec(
        self,
        cluster_name: str,
        role: str,
        command: list[str],
        *,
        privileged: bool = False,
        user: str = "",
        workdir: str = "",
        environment: dict[str, str] | None = None,
        timeout: int = 60,
    ) -> ExecResult:
        """Execute ``command`` (argv) inside a KIND node container.

        The command is passed as a list, not a shell string, to avoid shell
        injection and ensure portability.
        """
        container = self._get_container(cluster_name, role)
        try:
            return container.exec_run(
                command,
                privileged=privileged,
                user=user or None,
                workdir=workdir or None,
                environment=environment,
                demux=True,
            )
        except docker.errors.DockerException as exc:
            raise DockerClientError(f"Docker exec failed in {role}: {exc}") from exc

    def stop_container(self, cluster_name: str, role: str) -> None:
        """Stop a KIND node container."""
        container = self._get_container(cluster_name, role)
        try:
            container.stop()
        except docker.errors.DockerException as exc:
            raise DockerClientError(f"Could not stop {role}: {exc}") from exc

    def start_container(self, cluster_name: str, role: str) -> None:
        """Start a KIND node container."""
        container = self._get_container(cluster_name, role)
        try:
            container.start()
        except docker.errors.DockerException as exc:
            raise DockerClientError(f"Could not start {role}: {exc}") from exc

    def restart_container(self, cluster_name: str, role: str) -> None:
        """Restart a KIND node container."""
        container = self._get_container(cluster_name, role)
        try:
            container.restart()
        except docker.errors.DockerException as exc:
            raise DockerClientError(f"Could not restart {role}: {exc}") from exc

    def put_file(
        self,
        cluster_name: str,
        role: str,
        path: str,
        content: str,
        *,
        mode: str = "644",
    ) -> None:
        """Create or overwrite a file inside a KIND node container."""
        container = self._get_container(cluster_name, role)
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=path.lstrip("/"))
            info.size = len(data)
            info.mtime = 0
            try:
                info.mode = int(mode, 8)
            except ValueError:
                info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
        tar_stream.seek(0)
        try:
            container.put_archive("/", tar_stream)
        except docker.errors.DockerException as exc:
            raise DockerClientError(f"Could not write file to {role}: {exc}") from exc

    def list_containers(self, cluster_name: str) -> list[str]:
        """Return the names of all containers belonging to the cluster."""
        return [
            c.name
            for c in self._client.containers.list(all=True)
            if c.name and c.name.startswith(f"{cluster_name}-")
        ]


__all__ = ["DockerClient", "DockerClientError"]
