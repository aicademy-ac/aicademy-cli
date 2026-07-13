#!/usr/bin/env python3
"""End-to-end smoke test for the Aicademy CLI practice flow.

Runs the full lifecycle for one or more questions:
  logout -> login -> question start -> kubectl work -> verify -> clear -> logout

Defaults to 3 simple CKA questions. Requires Docker Desktop and the app dev server
to be runnable. The script starts the local API automatically, seeds a test CLI
token, runs the flows, and cleans up.

Usage:
    uv run python scripts/smoke_test.py
    uv run python scripts/smoke_test.py --questions cka-01 cka-02 cka-04
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Paths
CLI_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = CLI_ROOT.parent / "www.aicademy.ac"
LOCAL_DB = APP_ROOT / "local.db"
CONFIG_DIR = Path.home() / ".aicademy"
CONFIG_FILE = CONFIG_DIR / "config.json"
KUBECONFIG_PATH = CONFIG_DIR / "kubeconfig-aicademy-session"

API_URL = "http://localhost:3000"
USER_ID = "fppDybUxeu2MYIbvlWDw4XuikcJxhbKX"

# Simple questions with deterministic kubectl solutions.
DEFAULT_QUESTIONS = ["cka-01", "cka-02", "cka-04"]

QUESTION_SOLUTIONS: dict[str, list[list[str]]] = {
    "cka-01": [
        ["kubectl", "create", "namespace", "labs"],
        # poll handled separately after namespace creation
        ["kubectl", "run", "web", "--image=nginx:1.25", "-n", "labs", "--restart=Never"],
        ["kubectl", "wait", "--for=condition=Ready", "pod/web", "-n", "labs", "--timeout=60s"],
    ],
    "cka-02": [
        ["kubectl", "create", "deployment", "api-server", "--image=httpd:2.4", "--replicas=3"],
        [
            "kubectl",
            "wait",
            "deployment/api-server",
            "--for=condition=Available",
            "--timeout=60s",
        ],
    ],
    "cka-04": [
        [
            "kubectl",
            "create",
            "configmap",
            "nginx-conf",
            "--from-literal=default.conf=server { listen 80; location / { return 200 \"OK\"; } }",
        ],
    ],
}


def fail(message: str) -> None:
    print(f"[FAIL] {message}", file=sys.stderr)
    sys.exit(1)


def run(
    cmd: list[str] | str,
    *,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 300,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a shell command and stream output."""
    merged_env = os.environ.copy()
    merged_env["AICADEMY_API_URL"] = API_URL
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        merged_env.update(env)

    if isinstance(cmd, str):
        cmd = [cmd]

    print(f"\n[RUN] {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=str(cwd or CLI_ROOT),
        env=merged_env,
        input=input_text,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def check_prerequisites() -> None:
    for tool in ["docker", "kind", "kubectl", "bun", "python"]:
        if not shutil.which(tool):
            fail(f"Missing required tool: {tool}")
    if not LOCAL_DB.exists():
        fail(f"Local app DB not found: {LOCAL_DB}")

    # Verify Docker daemon is reachable (Docker Desktop must be running).
    try:
        subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
    except subprocess.CalledProcessError:
        fail("Docker daemon is not reachable. Start Docker Desktop first.")
    except subprocess.TimeoutExpired:
        fail("Docker daemon timed out. Start Docker Desktop first.")


def seed_cli_token() -> str:
    token = f"cli-test-{uuid.uuid4().hex}"
    now = int(time.time())
    expires_at = now + 30 * 24 * 60 * 60
    conn = sqlite3.connect(LOCAL_DB)
    conn.execute(
        """
        INSERT INTO session (
            id, expires_at, token, created_at, updated_at, ip_address, user_agent, user_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (uuid.uuid4().hex, expires_at, token, now, now, "127.0.0.1", "aicademy-cli", USER_ID),
    )
    conn.commit()
    conn.close()
    print("[INFO] Seeded test CLI token")
    return token


def cleanup_cli_token(token: str) -> None:
    conn = sqlite3.connect(LOCAL_DB)
    conn.execute("DELETE FROM session WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    print("[INFO] Cleaned up test CLI token")


def start_dev_server() -> subprocess.Popen:
    print("[INFO] Starting app dev server...")
    log_path = APP_ROOT / "dev-server.log"
    err_path = APP_ROOT / "dev-server.err"
    proc = subprocess.Popen(
        ["bun", "run", "dev"],
        cwd=APP_ROOT,
        stdout=open(log_path, "w", encoding="utf-8", errors="replace"),
        stderr=open(err_path, "w", encoding="utf-8", errors="replace"),
    )

    # Wait for the server to be ready
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            import urllib.request

            urllib.request.urlopen(API_URL, timeout=2)
            print(f"[INFO] Dev server ready at {API_URL}")
            return proc
        except Exception:
            time.sleep(1)

    proc.terminate()
    fail("Dev server did not start within 60 seconds")


def stop_dev_server(proc: subprocess.Popen) -> None:
    print("[INFO] Stopping app dev server...")
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


def reset_cli_config() -> None:
    if CONFIG_FILE.exists():
        CONFIG_FILE.unlink()


def cleanup_test_sessions() -> None:
    """Mark any active practice sessions for the test user as abandoned."""
    conn = sqlite3.connect(LOCAL_DB)
    conn.execute(
        """
        UPDATE practice_sessions
        SET status = 'abandoned', completed_at = ?
        WHERE user_id = ? AND status = 'active'
        """,
        (int(time.time()), USER_ID),
    )
    conn.commit()
    conn.close()
    print("[INFO] Cleaned up active practice sessions for test user")


def delete_existing_kind_clusters(questions: list[str]) -> None:
    """Remove leftover KIND clusters from prior smoke test runs."""
    for qid in questions:
        cluster_name = f"aicademy-{qid}"
        print(f"[INFO] Ensuring no leftover KIND cluster: {cluster_name}")
        subprocess.run(
            ["kind", "delete", "cluster", "--name", cluster_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def aicademy(
    *args: str,
    input_text: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return run(["uv", "run", "aicademy", *args], input_text=input_text, check=check)


def wait_for_resource(cmd: list[str], timeout: int = 30) -> None:
    """Poll until a kubectl get command succeeds."""
    env = {"KUBECONFIG": str(KUBECONFIG_PATH)}
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            cmd,
            cwd=str(CLI_ROOT),
            env={**os.environ, "KUBECONFIG": str(KUBECONFIG_PATH), "AICADEMY_API_URL": API_URL},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise RuntimeError(f"Resource not ready after {timeout}s: {' '.join(cmd)}")


def run_kubectl_work(commands: list[list[str]]) -> None:
    env = {"KUBECONFIG": str(KUBECONFIG_PATH)}
    for cmd in commands:
        run(cmd, env=env, cwd=CLI_ROOT)
        # Give the namespace controller time to create the default serviceaccount
        if len(cmd) >= 3 and cmd[0] == "kubectl" and cmd[1] == "create" and cmd[2] == "namespace":
            wait_for_resource(["kubectl", "get", "serviceaccount", "default", "-n", cmd[3]])


def run_question_flow(question_id: str) -> None:
    print(f"\n{'='*60}")
    print(f"[FLOW] Question: {question_id}")
    print(f"{'='*60}")

    solution = QUESTION_SOLUTIONS.get(question_id)
    if not solution:
        fail(f"No automated solution defined for {question_id}")

    # 1. Start question (provide 'y' in case a stale session conflict prompt appears)
    aicademy("question", "start", question_id, input_text="y\n")

    # 2. Apply kubectl work
    run_kubectl_work(solution)

    # 3. Verify (decline the interactive cleanup prompt so we control it)
    result = aicademy("verify", input_text="n\n", check=False)
    if result.returncode != 0:
        fail(f"Verification failed for {question_id}")

    # 4. Clear environment
    aicademy("question", "clear")

    print(f"[PASS] {question_id} completed successfully")


def configure_stdio() -> None:
    """Force UTF-8 for stdout/stderr so Windows consoles can handle rich CLI output."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def main() -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="Aicademy CLI end-to-end smoke test")
    parser.add_argument(
        "--questions",
        nargs="+",
        default=DEFAULT_QUESTIONS,
        help="Question IDs to test",
    )
    parser.add_argument(
        "--skip-server",
        action="store_true",
        help="Assume the app dev server is already running",
    )
    args = parser.parse_args()

    check_prerequisites()

    server_proc = None
    token: str | None = None
    failed_question: str | None = None

    try:
        if not args.skip_server:
            server_proc = start_dev_server()

        reset_cli_config()
        cleanup_test_sessions()
        delete_existing_kind_clusters(args.questions)
        token = seed_cli_token()

        # logout -> login
        aicademy("logout", check=False)
        aicademy("login", "--token", token)

        # Run each question flow
        for qid in args.questions:
            try:
                run_question_flow(qid)
            except Exception:
                failed_question = qid
                raise

        # Final logout
        aicademy("logout", check=False)
        print("\n[ALL PASS] Smoke test completed successfully")

    except Exception as exc:
        print(f"\n[FAIL] Smoke test failed: {exc}", file=sys.stderr)
        if failed_question:
            print(f"[FAIL] Failed at question: {failed_question}", file=sys.stderr)
        sys.exit(1)

    finally:
        if token:
            cleanup_cli_token(token)
        reset_cli_config()
        if server_proc:
            stop_dev_server(server_proc)


if __name__ == "__main__":
    main()
