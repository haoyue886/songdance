"""Opt-in isolated PostgreSQL/Redis tests. Never use an existing service or database."""

import os
import shutil
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from redis import Redis

from app.main import create_app
from app.services.auth import SupabaseVerifier
from app.services.auth_coordination import AuthCoordinator
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from tests.conftest import RecordingQueue
from tests.test_auth_ownership import FakeVerifier, auth_settings, create_job

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to temporary PostgreSQL/Redis instances; no existing services are used",
)


def free_port():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return server.getsockname()[1]


@pytest.fixture(scope="module")
def postgres(tmp_path_factory):
    if not shutil.which("initdb") or not shutil.which("pg_ctl"):
        pytest.skip("PostgreSQL binaries unavailable")
    root = tmp_path_factory.mktemp("auth-postgres")
    cluster = root / "cluster"
    port = free_port()
    subprocess.run(
        ["initdb", "-D", str(cluster), "-U", "postgres", "-A", "trust", "--no-sync"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "pg_ctl",
            "-D",
            str(cluster),
            "-l",
            str(root / "server.log"),
            "-o",
            f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''",
            "-w",
            "start",
        ],
        check=True,
        capture_output=True,
    )
    try:
        admin = f"postgresql://postgres@127.0.0.1:{port}/postgres"
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute("CREATE SCHEMA auth")
            connection.execute(
                "CREATE TABLE auth.users (id uuid PRIMARY KEY, email_confirmed_at timestamptz, "
                "banned_until timestamptz, deleted_at timestamptz, encrypted_password text)"
            )
            connection.execute(
                "CREATE TABLE auth.sessions (id uuid PRIMARY KEY, "
                "user_id uuid REFERENCES auth.users(id), created_at timestamptz, "
                "refreshed_at timestamptz, not_after timestamptz)"
            )
            sql = Path(__file__).resolve().parents[2] / "infra/supabase-session-reader.sql"
            connection.execute(sql.read_text())
            connection.execute("CREATE ROLE session_reader LOGIN")
            connection.execute("GRANT songdance_auth_reader TO session_reader")
        yield admin, f"postgresql://session_reader:test-only@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            ["pg_ctl", "-D", str(cluster), "-m", "fast", "-w", "stop"],
            check=True,
            capture_output=True,
        )


def test_real_session_query_rejects_revocation_and_has_no_password_or_write_access(
    postgres, tmp_path
):
    admin, reader = postgres
    user_id, session_id = uuid4(), uuid4()
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO auth.users (id, email_confirmed_at) VALUES (%s, now())", (user_id,)
        )
        connection.execute(
            "INSERT INTO auth.sessions VALUES (%s, %s, now(), now(), NULL)", (session_id, user_id)
        )
    verifier = SupabaseVerifier(
        auth_settings(tmp_path).model_copy(update={"auth_session_database_url": SecretStr(reader)})
    )
    try:
        assert verifier.session_active(str(user_id), str(session_id)) is True
        assert verifier.session_active(str(uuid4()), str(session_id)) is False
        with psycopg.connect(reader, autocommit=True) as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT encrypted_password FROM auth.users")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("DELETE FROM auth.sessions")
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(
                "UPDATE auth.sessions SET not_after = now() - interval '1 second' WHERE id = %s",
                (session_id,),
            )
        assert verifier.session_active(str(user_id), str(session_id)) is False
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute("DELETE FROM auth.sessions WHERE id = %s", (session_id,))
        assert verifier.session_active(str(user_id), str(session_id)) is False
    finally:
        verifier.engine.dispose()


def test_real_postgres_claim_race_has_one_owner(postgres, tmp_path):
    admin, reader = postgres
    subprocess.run(
        [".venv/bin/alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "SONGDANCE_DATABASE_URL": admin, "SONGDANCE_AUTH_ENABLED": "false"},
        check=True,
        capture_output=True,
    )
    settings = auth_settings(tmp_path).model_copy(
        update={
            "database_url": admin.replace("postgresql://", "postgresql+psycopg://"),
            "auth_session_database_url": SecretStr(reader),
            "auto_create_schema": False,
        }
    )
    app = create_app(
        settings,
        LocalObjectStorage(settings.local_storage_path),
        RecordingQueue(),
        MemoryJobQuota(settings),
    )
    original = app.state.auth_verifier
    app.state.auth_verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    try:
        with TestClient(app) as client:
            for who in ("alice", "bob"):
                assert (
                    client.get("/me", headers={"Authorization": f"Bearer {who}"}).status_code == 200
                )
            job = create_job(client).json()

            def claim(who):
                return client.post(
                    f"/jobs/{job['id']}/claim",
                    headers={
                        "Authorization": f"Bearer {who}",
                        "X-Job-Access": job["guest_access_token"],
                    },
                ).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(claim, ["alice", "bob"]))
            assert sorted(outcomes) == [200, 404]
    finally:
        app.state.engine.dispose()
        original.engine.dispose()


def test_two_coordinators_share_real_redis_refresh_lock_and_cache(tmp_path, monkeypatch):
    if not shutil.which("redis-server"):
        pytest.skip("Redis binary unavailable")
    port = free_port()
    process = subprocess.Popen(
        [
            "redis-server",
            "--bind",
            "127.0.0.1",
            "--port",
            str(port),
            "--save",
            "",
            "--appendonly",
            "no",
            "--dir",
            str(tmp_path),
            "--loglevel",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"redis://127.0.0.1:{port}/0"
    redis = Redis.from_url(url)
    try:
        ready = False
        for _ in range(100):
            try:
                ready = redis.ping()
                if ready:
                    break
            except Exception:
                time.sleep(0.05)
        assert ready
        settings = auth_settings(tmp_path).model_copy(
            update={"quota_backend": "redis", "redis_url": url, "quota_namespace": uuid4().hex}
        )
        instances = [AuthCoordinator(settings), AuthCoordinator(settings)]
        calls = []

        def post(*args, **kwargs):
            calls.append(1)
            time.sleep(0.05)
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"access_token": "private-access", "refresh_token": "private-refresh"},
            )

        monkeypatch.setattr("app.services.auth_coordination.requests.post", post)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(
                pool.map(lambda index: instances[index % 2].refresh("old-secret"), range(4))
            )
        assert len(calls) == 1 and len(results) == 4
        assert all(b"private-refresh" not in value for value in redis.mget(redis.keys("*")))
        for instance in instances:
            instance.redis.close()
    finally:
        redis.close()
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
