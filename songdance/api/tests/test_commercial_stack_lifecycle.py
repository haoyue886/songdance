"""Opt-in signal/forced-exit recovery checks for this task's disposable services."""

import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import requests
from redis import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to temporary HTTP/PostgreSQL/Redis process lifecycle checks",
)
API_ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.mark.parametrize(
    "exit_signal,active_worker",
    [
        (signal.SIGTERM, False),
        (signal.SIGINT, False),
        (signal.SIGKILL, False),
        (signal.SIGKILL, True),
    ],
)
def test_temporary_services_are_stopped_after_signal_or_explicit_recovery(
    tmp_path, exit_signal, active_worker
):
    root = tmp_path / "songdance-commercial-lifecycle"
    root.mkdir()
    port = free_port()
    environment = {
        **os.environ,
        "SONGDANCE_COMMERCIAL_CONTROL_SECRET": secrets.token_hex(32),
        "SONGDANCE_COMMERCIAL_BRIDGE_SECRET": secrets.token_hex(32),
        "SONGDANCE_COMMERCIAL_WORKER_HOLD_SECONDS": "90" if active_worker else "0",
    }
    worker_request = None
    pool = ThreadPoolExecutor(max_workers=1)
    with (root / "api.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.support.commercial_stack",
                "--root",
                str(root),
                "--site-url",
                "http://127.0.0.1:39999",
                "--port",
                str(port),
            ],
            cwd=API_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 45
            while True:
                assert process.poll() is None, "test API exited before readiness"
                try:
                    if requests.get(f"http://127.0.0.1:{port}/health", timeout=1).ok:
                        break
                except requests.RequestException:
                    pass
                assert time.monotonic() < deadline, "test API readiness timeout"
                time.sleep(0.05)
            resources = json.loads((root / "resources.json").read_text())
            connection = Redis(
                host="127.0.0.1",
                port=resources["redis_port"],
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            assert connection.info("server")["run_id"] == resources["redis_run_id"]
            if active_worker:
                worker_request = pool.submit(
                    requests.post,
                    f"http://127.0.0.1:{port}/__commercial__/control",
                    json={"action": "transcription_worker"},
                    headers={
                        "Authorization": "Bearer "
                        + environment["SONGDANCE_COMMERCIAL_CONTROL_SECRET"]
                    },
                    timeout=20,
                )
                deadline = time.monotonic() + 10
                while True:
                    resources = json.loads((root / "resources.json").read_text())
                    if resources.get("worker_pid"):
                        os.kill(resources["worker_pid"], 0)
                        break
                    assert time.monotonic() < deadline, "Worker did not register its identity"
                    time.sleep(0.05)
            process.send_signal(exit_signal)
            process.wait(timeout=20)
            if exit_signal != signal.SIGKILL:
                assert process.returncode == 0
                assert json.loads((root / "resources.json").read_text())["stopped"] is True
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.support.commercial_stack",
                    "--cleanup-root",
                    str(root),
                ],
                cwd=API_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
            )
            assert result.returncode == 0, "owned test resource recovery failed"
            assert json.loads(result.stdout)["stopped"] is True
            assert not (root / "cluster/postmaster.pid").exists()
            if active_worker:
                result = subprocess.run(
                    ["ps", "-p", str(resources["worker_pid"]), "-o", "stat="],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    assert "Z" in result.stdout
                else:
                    with pytest.raises(ProcessLookupError):
                        os.kill(resources["worker_pid"], 0)
            with pytest.raises(RedisConnectionError):
                connection.ping()
            connection.close()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.support.commercial_stack",
                    "--cleanup-root",
                    str(root),
                ],
                cwd=API_ROOT,
                env=environment,
                capture_output=True,
                timeout=20,
                check=True,
            )
            if worker_request:
                try:
                    worker_request.result(timeout=5)
                except requests.RequestException:
                    pass
            pool.shutdown(wait=True)


def test_failed_process_inspection_cannot_report_a_live_worker_stopped(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from tests.support import commercial_stack

    root = tmp_path / "songdance-commercial-worker-inspection"
    root.mkdir()
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    (root / "resources.json").write_text(
        json.dumps(
            {
                "root": str(root.resolve()),
                "worker_pid": process.pid,
                "stopped": False,
            }
        )
    )
    monkeypatch.setattr(
        commercial_stack.subprocess,
        "run",
        lambda *_, **__: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="inspection denied",
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="could not be verified"):
            commercial_stack.cleanup_resources(root)
        assert process.poll() is None
        assert json.loads((root / "resources.json").read_text())["stopped"] is False
    finally:
        commercial_stack.stop_group(process)
