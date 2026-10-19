"""Two loopback HTTP API processes, local signed JWTs and disposable PostgreSQL."""

import hashlib
import multiprocessing
import os
import re
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import SecretStr
from sqlalchemy import event

from app.database import create_db_engine, create_session_factory
from app.main import create_app
from app.models import SourceAsset, TranscriptionJob
from app.services.job_access import new_guest_secret
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from tests import test_auth_real_services as real_services
from tests.conftest import RecordingQueue, wav_bytes
from tests.test_auth_ownership import auth_settings

postgres = real_services.postgres
pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to two local HTTP processes and disposable PostgreSQL",
)


def serve_instance(settings, public_key, listener, barrier, messages, label):
    """Spawn target: no parent engines, clients or verifier state are inherited."""
    import uvicorn

    app = create_app(settings, LocalObjectStorage(settings.local_storage_path),
                     RecordingQueue(), MemoryJobQuota(settings))
    verifier = app.state.auth_verifier
    key = serialization.load_pem_public_key(public_key)
    verifier.jwks = SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key))
    claim_context = ContextVar("multi_api_claim", default=None)

    @app.middleware("http")
    async def identify_instance(request, call_next):
        request_id = request.headers.get("x-request-id", "")
        match = re.fullmatch(r"multi-api-([ab])-r([123])-initial", request_id)
        initial = bool(match and match[1] == label and request.method == "POST"
                       and re.fullmatch(r"/jobs/[^/]+/claim", request.url.path))
        marker = claim_context.set(request_id if initial else None)
        try:
            response = await call_next(request)
            if initial:
                messages.put({"phase": "response", "request_id": request_id,
                              "pid": os.getpid(), "status": response.status_code,
                              "at": time.monotonic_ns()})
            response.headers["X-Test-Instance"] = label
            response.headers["X-Test-Pid"] = str(os.getpid())
            return response
        finally:
            claim_context.reset(marker)

    def synchronize_job_lock(conn, cursor, statement, parameters, context, many):
        request_id = claim_context.get()
        if request_id and statement.startswith("SELECT transcription_jobs.") \
                and "FOR UPDATE" in statement:
            messages.put({"phase": "before_job_lock", "request_id": request_id,
                          "pid": os.getpid(),
                          "backend_pid": conn.connection.driver_connection.info.backend_pid,
                          "at": time.monotonic_ns()})
            barrier.wait(timeout=15)

    event.listen(app.state.engine, "before_cursor_execute", synchronize_job_lock)
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False,
            proxy_headers=False, lifespan="off")).run(sockets=[listener])
    finally:
        event.remove(app.state.engine, "before_cursor_execute", synchronize_job_lock)
        verifier.engine.dispose()
        app.state.engine.dispose()
        listener.close()


def stop_instance(process):
    if process.is_alive():
        process.terminate()
    process.join(timeout=10)
    if process.is_alive():
        process.kill()
        process.join(timeout=5)
    assert not process.is_alive(), "Test API process failed to stop"


@pytest.mark.parametrize("postgres", ["songdance_auth"], indirect=True)
def test_two_api_processes_share_one_atomic_claim_owner(postgres, tmp_path):
    admin, reader = postgres
    api = Path(__file__).resolve().parents[1]
    subprocess.run([str(api / ".venv/bin/alembic"), "upgrade", "head"], cwd=api,
        env={**os.environ, "SONGDANCE_DATABASE_URL": admin, "SONGDANCE_AUTH_ENABLED": "false"},
        check=True, capture_output=True)
    settings = auth_settings(tmp_path).model_copy(update={
        "database_url": admin.replace("postgresql://", "postgresql+psycopg://"),
        "auth_session_database_url": SecretStr(reader), "auth_session_schema": "songdance_auth",
        "auto_create_schema": False,
    })
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    identities = {label: (uuid4(), uuid4()) for label in ("alice", "bob")}
    with psycopg.connect(admin) as connection:
        for subject, sid in identities.values():
            connection.execute("INSERT INTO auth.users(id,email_confirmed_at) VALUES(%s,now())",
                               (subject,))
            connection.execute("INSERT INTO auth.sessions VALUES(%s,%s,now(),now(),NULL)",
                               (sid, subject))
    headers = {label: {"Authorization": "Bearer " + jwt.encode({
        "iss": "https://auth.example/auth/v1", "aud": "authenticated", "role": "authenticated",
        "sub": str(subject), "session_id": str(sid), "email": "same@example.test",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }, private_key, algorithm="RS256")} for label, (subject, sid) in identities.items()}
    context = multiprocessing.get_context("spawn")
    barrier, messages = context.Barrier(2), context.Queue()
    processes, urls = {}, {}
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    storage = LocalObjectStorage(settings.local_storage_path)
    # trust_env=False keeps every HTTP request on loopback, even on proxy-enabled hosts.
    with httpx.Client(trust_env=False, timeout=25) as client:
        def start(label):
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            urls[label] = f"http://127.0.0.1:{listener.getsockname()[1]}"
            process = context.Process(target=serve_instance, args=(
                settings, public_key, listener, barrier, messages, label))
            try:
                process.start()
                processes[label] = process
            finally:
                listener.close()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                assert process.is_alive(), "API process exited during startup"
                try:
                    response = client.get(urls[label] + "/health", timeout=0.5)
                    if response.status_code == 200:
                        assert response.headers["X-Test-Instance"] == label
                        assert int(response.headers["X-Test-Pid"]) == process.pid
                        return
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            pytest.fail("API process did not become ready")

        def request(instance, method, path, who=None, extra=None):
            response = client.request(method, urls[instance] + path,
                                      headers={**headers.get(who, {}), **(extra or {})})
            assert response.headers["X-Test-Instance"] == instance
            assert int(response.headers["X-Test-Pid"]) == processes[instance].pid
            return response

        try:
            start("a")
            start("b")
            assert len({process.pid for process in processes.values()}) == 2
            owners = {}
            for who in identities:
                accounts = [request(instance, "GET", "/me", who) for instance in ("a", "b")]
                assert all(response.status_code == 200 for response in accounts)
                assert accounts[0].json()["id"] == accounts[1].json()["id"]
                owners[who] = accounts[0].json()["id"]
            assert owners["alice"] != owners["bob"]
            fixtures = []
            audio = tmp_path / "synthetic.wav"
            audio.write_bytes(wav_bytes())
            for number, order in enumerate((("alice", "bob"), ("bob", "alice"),
                                           ("alice", "bob")), start=1):
                job_id = "multi_api_" + uuid4().hex
                capability, hashed = new_guest_secret()
                storage_key = f"jobs/{job_id}/source.wav"
                storage.put_file(storage_key, audio, "audio/wav")
                with factory.begin() as session:
                    job = TranscriptionJob(id=job_id, guest_secret_hash=hashed,
                        status="queued", stage="queued", source_type="upload", start_sec=0,
                        end_sec=2, attempt_count=1, expires_at=datetime.now(UTC)+timedelta(hours=1))
                    job.source_asset = SourceAsset(id=uuid4().hex, storage_key=storage_key,
                        mime_type="audio/wav", size_bytes=audio.stat().st_size,
                        duration_sec=2, sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
                    session.add(job)
                path = "/jobs/" + job_id
                guest = {"X-Job-Access": capability}

                def claim(pair, *, number=number, path=path, guest=guest):
                    instance, who = pair
                    return request(instance, "POST", path + "/claim", who, {
                        **guest, "X-Request-ID": f"multi-api-{instance}-r{number}-initial"})

                with ThreadPoolExecutor(max_workers=2) as pool:
                    outcomes = list(pool.map(claim, zip(("a", "b"), order, strict=True)))
                statuses = [response.status_code for response in outcomes]
                assert sorted(statuses) == [200, 404]
                winner = order[statuses.index(200)]
                events = [messages.get(timeout=5) for _ in range(4)]
                arrived = [row for row in events if row["phase"] == "before_job_lock"]
                responded = [row for row in events if row["phase"] == "response"]
                expected_ids = {f"multi-api-{label}-r{number}-initial" for label in ("a", "b")}
                assert len(arrived) == len(responded) == 2
                assert {row["request_id"] for row in arrived} == expected_ids
                assert {row["request_id"] for row in responded} == expected_ids
                assert {row["pid"] for row in arrived} == {p.pid for p in processes.values()}
                assert len({row["backend_pid"] for row in arrived}) == 2
                assert max(row["at"] for row in arrived) < min(row["at"] for row in responded)
                assert sorted(row["status"] for row in responded) == [200, 404]
                for instance in ("a", "b"):
                    for who in order:
                        expected = 200 if who == winner else 404
                        assert request(instance, "GET", path, who).status_code == expected
                        assert request(instance, "POST", path + "/claim", who,
                                       guest).status_code == expected
                    assert request(instance, "GET", path, extra=guest).status_code == 404
                with factory() as session:
                    stored = session.get(TranscriptionJob, job_id)
                    assert stored.owner_user_id == owners[winner]
                    assert stored.guest_secret_hash is None
                    assert (stored.status, stored.stage, stored.attempt_count) == (
                        "queued", "queued", 1)
                    assert stored.source_asset.storage_key == storage_key
                assert storage.exists(storage_key)
                stored_audio = settings.local_storage_path / storage_key
                assert stored_audio.read_bytes() == audio.read_bytes()
                fixtures.append((path, winner))
            # State must survive replacement of an API process and its connection pools.
            old_pid = processes["a"].pid
            stop_instance(processes["a"])
            start("a")
            assert processes["a"].pid != old_pid
            for path, winner in fixtures:
                for who in identities:
                    expected = 200 if who == winner else 404
                    assert request("a", "GET", path, who).status_code == expected
                    assert request("a", "POST", path+"/claim", who).status_code == expected
        finally:
            for process in processes.values():
                stop_instance(process)
            messages.close()
            messages.join_thread()
            engine.dispose()
