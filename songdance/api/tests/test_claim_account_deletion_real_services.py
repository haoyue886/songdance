"""Claim/delete ordering through independent app engines and disposable PostgreSQL."""

import hashlib
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, select

from app.main import create_app
from app.models import AccountDeletion, AuthIdentity, SourceAsset, TranscriptionJob, User
from app.services.account_deletion import process_account_deletions
from app.services.job_access import new_guest_secret
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.settings import Settings
from tests import test_auth_real_services as real_services
from tests.conftest import RecordingQueue, wav_bytes
from tests.test_auth_ownership import auth_settings

postgres = real_services.postgres
pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable local PostgreSQL; no real user accounts are deleted",
)


@pytest.mark.parametrize("postgres", ["songdance_auth"], indirect=True)
@pytest.mark.parametrize("first_operation", ["claim", "delete"])
def test_claim_and_delete_serialize_then_cleanup_only_owned_jobs(
    postgres, tmp_path, first_operation
):
    admin, reader = postgres
    api = Path(__file__).resolve().parents[1]
    subprocess.run([str(api / ".venv/bin/alembic"), "upgrade", "head"], cwd=api,
        env={**os.environ, "SONGDANCE_DATABASE_URL": admin, "SONGDANCE_AUTH_ENABLED": "false"},
        check=True, capture_output=True)
    settings = Settings(_env_file=None, **{
        **auth_settings(tmp_path).model_dump(),
        "database_url": admin.replace("postgresql://", "postgresql+psycopg://"),
        "auth_session_database_url": SecretStr(reader), "auth_session_schema": "songdance_auth",
        "auto_create_schema": False, "account_deletion_enabled": True,
        "usage_enabled": True, "reliable_queue_enabled": True,
    })
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subjects = {label: (uuid4(), uuid4()) for label in ("alice", "bob")}
    with psycopg.connect(admin) as connection:
        for subject, sid in subjects.values():
            connection.execute("INSERT INTO auth.users(id,email_confirmed_at) VALUES(%s,now())",
                               (subject,))
            connection.execute("INSERT INTO auth.sessions VALUES(%s,%s,now(),now(),NULL)",
                               (sid, subject))
    headers = {label: {"Authorization": "Bearer " + jwt.encode({
        "iss": "https://auth.example/auth/v1", "aud": "authenticated", "role": "authenticated",
        "sub": str(subject), "session_id": str(sid), "email": label + "@example.test",
        "exp": datetime.now(UTC) + timedelta(minutes=5),
    }, key, algorithm="RS256"), "Origin": "http://localhost:3000"}
        for label, (subject, sid) in subjects.items()}
    apps = []
    for _ in range(2):
        app = create_app(settings, LocalObjectStorage(settings.local_storage_path),
                         RecordingQueue(), MemoryJobQuota(settings))
        app.state.auth_verifier.jwks = SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()))
        apps.append(app)
    assert apps[0].state.engine is not apps[1].state.engine
    first_locked, release_first, second_lock_attempt = Event(), Event(), Event()
    backend_pids = {}

    def hold_first_user_lock(conn, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT users.") and "FOR NO KEY UPDATE" in statement:
            backend_pids["first"] = conn.connection.driver_connection.info.backend_pid
            first_locked.set()
            assert release_first.wait(15), "First admission lock was not released"

    def observe_second_user_lock(conn, cursor, statement, parameters, context, many):
        if statement.startswith("SELECT users.") and "FOR NO KEY UPDATE" in statement:
            backend_pids["second"] = conn.connection.driver_connection.info.backend_pid
            second_lock_attempt.set()

    try:
        with TestClient(apps[0]) as first_client, TestClient(apps[1]) as second_client:
            owners = {}
            for label in subjects:
                response = first_client.get("/me", headers=headers[label])
                assert response.status_code == 200
                owners[label] = response.json()["id"]
            assert owners["alice"] != owners["bob"]
            state = apps[0].state
            audio = tmp_path / "synthetic.wav"
            audio.write_bytes(wav_bytes())
            guest_id, other_id = uuid4().hex, uuid4().hex
            capability, hashed = new_guest_secret()
            for job_id, owner, guest_hash in ((guest_id, None, hashed),
                                               (other_id, owners["bob"], None)):
                storage_key = f"jobs/{job_id}/source.wav"
                state.storage.put_file(storage_key, audio, "audio/wav")
                with state.session_factory.begin() as session:
                    job = TranscriptionJob(id=job_id, owner_user_id=owner,
                        guest_secret_hash=guest_hash, status="queued", stage="queued",
                        source_type="upload", start_sec=0, end_sec=2, attempt_count=1,
                        expires_at=datetime.now(UTC)+timedelta(hours=1))
                    job.source_asset = SourceAsset(id=uuid4().hex, storage_key=storage_key,
                        mime_type="audio/wav", size_bytes=audio.stat().st_size, duration_sec=2,
                        sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
                    session.add(job)
            path = "/jobs/" + guest_id
            guest_headers = {"X-Job-Access": capability}

            def operation(client, kind):
                if kind == "claim":
                    return client.post(path+"/claim", headers={**headers["alice"], **guest_headers})
                return client.request("DELETE", "/me", headers=headers["alice"],
                                      json={"confirmation": "DELETE"})

            event.listen(state.engine, "after_cursor_execute", hold_first_user_lock)
            event.listen(apps[1].state.engine, "before_cursor_execute", observe_second_user_lock)
            second_operation = "delete" if first_operation == "claim" else "claim"
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first = pool.submit(operation, first_client, first_operation)
                    try:
                        assert first_locked.wait(15)
                        second = pool.submit(operation, second_client, second_operation)
                        assert second_lock_attempt.wait(15)
                        assert backend_pids["first"] != backend_pids["second"]
                        # Prove a real SQL lock wait, not merely a scheduled second thread.
                        deadline = time.monotonic() + 5
                        with psycopg.connect(admin, autocommit=True) as connection:
                            while time.monotonic() < deadline:
                                blockers = connection.execute("SELECT pg_blocking_pids(%s)",
                                    (backend_pids["second"],)).fetchone()[0]
                                if backend_pids["first"] in blockers:
                                    break
                                time.sleep(0.01)
                            else:
                                pytest.fail("Second request did not wait on the first user's lock")
                        assert not first.done() and not second.done()
                    finally:
                        release_first.set()
                    first_response = first.result(timeout=15)
                    second_response = second.result(timeout=15)
            finally:
                release_first.set()
                event.remove(state.engine, "after_cursor_execute", hold_first_user_lock)
                event.remove(apps[1].state.engine, "before_cursor_execute",
                             observe_second_user_lock)
            if first_operation == "claim":
                assert first_response.status_code == 200
                assert second_response.status_code == 202
                accepted = second_response
            else:
                assert first_response.status_code == 202
                assert second_response.status_code == 409
                assert second_response.json()["detail"]["code"] == "ACCOUNT_DELETION_PENDING"
                accepted = first_response
            deletion_id = accepted.json()["deletion"]["id"]
            with state.session_factory() as session:
                job = session.get(TranscriptionJob, guest_id)
                expected_owner = owners["alice"] if first_operation == "claim" else None
                assert job.owner_user_id == expected_owner
                assert job.guest_secret_hash == (None if first_operation == "claim" else hashed)
                assert session.get(AccountDeletion, deletion_id).phase == "billing"
                assert session.get(User, owners["alice"]).active is True
            # From this point onward both app instances must close the admission gate.
            for client in (first_client, second_client):
                blocked = operation(client, "claim")
                assert blocked.status_code == 409
                assert blocked.json()["detail"]["code"] == "ACCOUNT_DELETION_PENDING"
            assert state.storage.exists(f"jobs/{guest_id}/source.wav")
            # No billing bindings: real deletion stages can run with provider=None.
            assert process_account_deletions(state.session_factory, state.storage, settings) == 1
            with state.session_factory() as session:
                row = session.get(AccountDeletion, deletion_id)
                assert (row.status, row.phase, row.attempts) == ("pending", "cleanup", 1)
                assert session.get(User, owners["alice"]).active is False
                assert session.get(TranscriptionJob, guest_id) is not None
            assert state.storage.exists(f"jobs/{guest_id}/source.wav")
            assert process_account_deletions(state.session_factory, state.storage, settings) == 1
            with state.session_factory() as session:
                row = session.get(AccountDeletion, deletion_id)
                assert (row.status, row.phase, row.attempts) == ("completed", "cleanup", 2)
                assert row.completed_at is not None
                user = session.get(User, owners["alice"])
                assert user.active is False and user.email is None
                assert session.scalar(select(AuthIdentity.user_id).where(
                    AuthIdentity.subject == str(subjects["alice"][0]))) == owners["alice"]
                job = session.get(TranscriptionJob, guest_id)
                if first_operation == "claim":
                    assert job is None
                else:
                    assert job.owner_user_id is None and job.guest_secret_hash == hashed
                other = session.get(TranscriptionJob, other_id)
                assert other.owner_user_id == owners["bob"] and other.status == "queued"
            assert state.storage.exists(f"jobs/{guest_id}/source.wav") is (
                first_operation == "delete")
            other_source = settings.local_storage_path / f"jobs/{other_id}/source.wav"
            assert other_source.read_bytes() == audio.read_bytes()
            for client in (first_client, second_client):
                progress = client.get("/me", headers=headers["alice"])
                assert progress.status_code == 200
                assert progress.json()["id"] == owners["alice"]
                assert progress.json()["deletion"]["status"] == "completed"
                assert operation(client, "claim").status_code == 403
                assert client.get("/jobs/"+other_id, headers=headers["bob"]).status_code == 200
                assert client.get(path, headers=guest_headers).status_code == (
                    200 if first_operation == "delete" else 404)
            assert process_account_deletions(state.session_factory, state.storage, settings) == 0
    finally:
        release_first.set()
        for app in apps:
            app.state.auth_verifier.engine.dispose()
            app.state.engine.dispose()
