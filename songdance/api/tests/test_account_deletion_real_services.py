"""Deletion races on disposable PostgreSQL; billing and identity network calls stay offline."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import jwt
import psycopg
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, select

from app.main import create_app
from app.models import (
    AccountDeletion,
    AccountDeletionSubscription,
    AuthIdentity,
    CheckoutSession,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
    User,
)
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent
from app.services.account_deletion import process_account_deletions
from app.services.auth import SupabaseVerifier
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from app.services.transcription_persistence import mark_failed, persist_result
from app.settings import Settings
from tests.conftest import RecordingQueue
from tests.test_account_deletion import create_job, process, request_deletion
from tests.test_auth_ownership import FakeVerifier, auth_settings
from tests.test_auth_real_services import postgres as postgres
from tests.test_creem_billing import HEADERS, SECRET, FakeProvider, pay
from tests.test_creem_billing import checkout as billing_checkout
from tests.test_creem_real_services import database as database

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)


@pytest.fixture
def client(database, tmp_path):
    url, _, _ = database
    settings = Settings(_env_file=None, **{
        **auth_settings(tmp_path).model_dump(),
        "database_url": url.replace("postgresql://", "postgresql+psycopg://"),
        "auto_create_schema": False,
        "usage_enabled": True,
        "paid_usage_enabled": True,
        "account_deletion_enabled": True,
        "reliable_queue_enabled": True,
        "creem_enabled": True,
        "billing_environment": "test",
        "creem_product_id": "prod_test",
        "creem_api_key": SecretStr("creem_test_offline"),
        "creem_webhook_secret": SecretStr(SECRET),
        "creem_success_url": "http://localhost:3000/billing/return",
        "daily_job_limit": 1000,
        "hourly_job_limit": 1000,
    })
    app = create_app(
        settings, LocalObjectStorage(settings.local_storage_path), RecordingQueue(),
        MemoryJobQuota(settings),
    )
    original = app.state.auth_verifier
    verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    verifier.reauthenticated_at = lambda identity: datetime.now(UTC)
    app.state.auth_verifier, app.state.creem_client = verifier, FakeProvider()
    try:
        with TestClient(app) as test_client:
            assert test_client.get("/me", headers=HEADERS).status_code == 200
            yield test_client
    finally:
        app.state.engine.dispose()
        original.engine.dispose()


def observe_lock(engine, reached, *, table, lock="FOR UPDATE"):
    def observe(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"SELECT {table}.") and lock in statement:
            reached.set()

    event.listen(engine, "before_cursor_execute", observe)
    return observe


@pytest.mark.parametrize("admission", ["checkout", "claim", "job"])
def test_deletion_request_lock_rechecks_admission_after_committing_tombstone(
    client, monkeypatch, admission
):
    import app.services.account_deletion as deletion_service

    state = client.app.state
    guest = create_job(client).json() if admission == "claim" else None
    entered, release, admitting = Event(), Event(), Event()
    original_lock = deletion_service.lock_usage_user

    def hold_deletion_lock(session, user_id):
        original_lock(session, user_id)
        entered.set()
        assert release.wait(15), "deletion admission lock was not released"

    monkeypatch.setattr(deletion_service, "lock_usage_user", hold_deletion_lock)

    def admit():
        with TestClient(client.app) as parallel:
            if admission == "checkout":
                return billing_checkout(parallel)
            if admission == "claim":
                return parallel.post(f"/jobs/{guest['id']}/claim", headers={
                    **HEADERS, "X-Job-Access": guest["guest_access_token"],
                })
            return create_job(parallel, "alice")

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleting = pool.submit(request_deletion, client)
        listener = None
        try:
            assert entered.wait(15)
            listener = observe_lock(
                state.engine, admitting, table="users", lock="FOR NO KEY UPDATE",
            )
            creating = pool.submit(admit)
            assert admitting.wait(15)
            assert not creating.done()
        finally:
            release.set()
            if listener:
                event.remove(state.engine, "before_cursor_execute", listener)
        assert deleting.result(timeout=15).status_code == 202
        response = creating.result(timeout=15)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACCOUNT_DELETION_PENDING"
    with state.session_factory() as session:
        assert len(session.scalars(select(AccountDeletion)).all()) == 1
        assert session.scalar(select(CheckoutSession)) is None
        owned = session.scalars(select(TranscriptionJob).where(
            TranscriptionJob.owner_user_id.is_not(None)
        )).all()
        assert owned == []
        if guest:
            assert session.get(TranscriptionJob, guest["id"]).owner_user_id is None
    assert state.creem_client.create_calls == []


def test_preexisting_checkout_in_flight_cannot_let_deletion_skip_billing(client, monkeypatch):
    state, provider = client.app.state, client.app.state.creem_client
    job = create_job(client, "alice").json()
    entered, release = Event(), Event()
    original = provider.create_checkout

    def held_checkout(**kwargs):
        entered.set()
        assert release.wait(15), "offline checkout was not released"
        return original(**kwargs)

    monkeypatch.setattr(provider, "create_checkout", held_checkout)
    with ThreadPoolExecutor(max_workers=1) as pool:
        checkout = pool.submit(billing_checkout, client)
        try:
            assert entered.wait(15)
            assert request_deletion(client).status_code == 202
            assert process(client, provider) == 1
            with state.session_factory() as session:
                intent = session.scalars(select(CheckoutSession)).one()
                deletion = session.scalars(select(AccountDeletion)).one()
                assert intent.status == "creating" and intent.provider_id is None
                assert (deletion.status, deletion.phase) == ("retry", "billing")
                assert session.get(User, deletion.user_id).active is True
                assert session.get(TranscriptionJob, job["id"]) is not None
            assert state.storage.exists(f"jobs/{job['id']}/source.wav")
        finally:
            release.set()
        assert checkout.result(timeout=15).status_code == 200
    provider.checkout["status"] = "completed"
    assert process(client, provider, now=datetime.now(UTC) + timedelta(hours=1)) == 1
    assert provider.cancel_calls == ["sub_test"]
    with state.session_factory() as session:
        row = session.scalars(select(AccountDeletion)).one()
        assert (row.status, row.phase) == ("pending", "cleanup")
        assert session.get(User, row.user_id).active is False


@pytest.mark.parametrize("operation", ["create", "retry"])
def test_non_usage_owned_job_admission_rechecks_delete_under_user_lock(
    client, monkeypatch, operation
):
    import app.services.account_deletion as deletion_service

    state = client.app.state
    deletion_settings = state.settings
    admission_settings = Settings(_env_file=None, **{
        **deletion_settings.model_dump(), "account_deletion_enabled": False,
        "usage_enabled": False, "paid_usage_enabled": False,
        "reliable_queue_enabled": False, "creem_enabled": False,
    })
    job = None
    if operation == "retry":
        state.settings = admission_settings
        try:
            job = create_job(client, "alice").json()
        finally:
            state.settings = deletion_settings
        mark_failed(state.session_factory, job["id"], "OFFLINE", "test failure", expected_attempt=1)
    entered, release, progressed = Event(), Event(), Event()
    observed = []
    original_lock = deletion_service.lock_usage_user

    def held_lock(session, user_id):
        original_lock(session, user_id)
        entered.set()
        assert release.wait(15), "deletion lock was not released"

    def observe_first_write_lock(conn, cursor, statement, parameters, context, executemany):
        if progressed.is_set():
            return
        if statement.startswith("SELECT users.") and "FOR NO KEY UPDATE" in statement:
            observed.append("owner_lock")
        elif statement.startswith("INSERT INTO transcription_jobs") or (
            statement.startswith("SELECT transcription_jobs.") and "FOR UPDATE" in statement
        ):
            observed.append("job_write")
        else:
            return
        progressed.set()

    monkeypatch.setattr(deletion_service, "lock_usage_user", held_lock)

    def admit():
        with TestClient(client.app) as parallel:
            if operation == "create":
                return create_job(parallel, "alice")
            return parallel.post(f"/jobs/{job['id']}/retry", headers=HEADERS)

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleting = pool.submit(request_deletion, client)
        listening = False
        try:
            assert entered.wait(15)
            # The deleting request already captured its valid Settings object.
            state.settings = admission_settings
            event.listen(state.engine, "before_cursor_execute", observe_first_write_lock)
            listening = True
            creating = pool.submit(admit)
            assert progressed.wait(15)
        finally:
            release.set()
            if listening:
                event.remove(state.engine, "before_cursor_execute", observe_first_write_lock)
        try:
            assert deleting.result(timeout=15).status_code == 202
            response = creating.result(timeout=15)
        finally:
            state.settings = deletion_settings
    assert observed == ["owner_lock"], response.text
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ACCOUNT_DELETION_PENDING"


def test_simultaneous_account_deletion_requests_create_one_per_user_row(client, monkeypatch):
    import app.services.account_deletion as deletion_service

    barrier = Barrier(2)
    original = deletion_service.lock_usage_user

    def synchronized_lock(session, user_id):
        barrier.wait(timeout=15)
        original(session, user_id)

    monkeypatch.setattr(deletion_service, "lock_usage_user", synchronized_lock)

    def delete(_):
        with TestClient(client.app) as parallel:
            return request_deletion(parallel)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(delete, range(2)))
    assert [response.status_code for response in responses] == [202, 202]
    assert responses[0].json()["deletion"]["id"] == responses[1].json()["deletion"]["id"]
    with client.app.state.session_factory() as session:
        rows = session.scalars(select(AccountDeletion)).all()
        assert len(rows) == 1 and rows[0].attempts == 0


def test_competing_deletion_workers_cancel_once_and_follow_committed_checkpoint(client):
    state, provider = client.app.state, client.app.state.creem_client
    pay(client, provider)
    assert request_deletion(client).status_code == 202
    barrier = Barrier(2)
    now = datetime.now(UTC)

    def synchronized_candidates(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT account_deletions.id, account_deletions.user_id")
            and "account_deletions.status IN" in statement
            and "FOR UPDATE" not in statement
        ):
            barrier.wait(timeout=15)

    event.listen(state.engine, "after_cursor_execute", synchronized_candidates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: process(client, provider, now=now), range(2)))
    finally:
        event.remove(state.engine, "after_cursor_execute", synchronized_candidates)
    assert counts == [1, 1]
    assert provider.cancel_calls == ["sub_test"]
    with state.session_factory() as session:
        row = session.scalars(select(AccountDeletion)).one()
        assert (row.status, row.phase, row.attempts) == ("completed", "cleanup", 2)
        assert session.scalars(select(AccountDeletionSubscription.status)).all() == ["verified"]


@pytest.mark.parametrize("storage_failure", [False, True])
def test_cleanup_job_lock_makes_late_worker_observe_delete_or_durable_failure_fence(
    client, monkeypatch, storage_failure
):
    state, provider = client.app.state, client.app.state.creem_client
    job = create_job(client, "alice").json()
    assert request_deletion(client).status_code == 202 and process(client, provider) == 1
    entered, release, committing = Event(), Event(), Event()
    original = state.storage.delete

    def held_delete(key):
        entered.set()
        assert release.wait(15), "cleanup storage was not released"
        if storage_failure:
            raise OSError("isolated object storage unavailable")
        return original(key)

    monkeypatch.setattr(state.storage, "delete", held_delete)
    scored = build_score([NoteEvent(0, 1, 60, 100, 0.9)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        cleaning = pool.submit(process, client, provider)
        listener = None
        try:
            assert entered.wait(15)
            listener = observe_lock(state.engine, committing, table="transcription_jobs")
            worker = pool.submit(
                persist_result, state.session_factory, state.storage, job["id"], scored, [],
                expected_attempt=1,
            )
            assert committing.wait(15)
            assert not worker.done()
        finally:
            release.set()
            if listener:
                event.remove(state.engine, "before_cursor_execute", listener)
        assert cleaning.result(timeout=15) == 1
        assert worker.result(timeout=15) is False
    with state.session_factory() as session:
        retained = session.get(TranscriptionJob, job["id"])
        row = session.scalars(select(AccountDeletion)).one()
        assert row.status == ("retry" if storage_failure else "completed")
        if storage_failure:
            assert (retained.status, retained.error_code) == ("failed", "DELETE_FAILED")
        else:
            assert retained is None
        assert sorted(session.scalars(select(UsageLedger.event_type)).all()) == [
            "release", "reservation",
        ]
        period = session.scalars(select(UsagePeriod)).one()
        assert (period.reserved_units, period.consumed_units) == (0, 0)


def auth_session(postgres, *, created_at):
    admin, reader = postgres
    user_id, session_id = uuid4(), uuid4()
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(
            "INSERT INTO auth.users (id,email_confirmed_at) VALUES (%s,now())", (user_id,),
        )
        connection.execute(
            "INSERT INTO auth.sessions (id,user_id,created_at,refreshed_at) "
            "VALUES (%s,%s,%s,now())",
            (session_id, user_id, created_at),
        )
    return reader, user_id, session_id


def signed_verifier(settings, reader, user_id, session_id):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = SupabaseVerifier(settings.model_copy(update={
        "auth_session_database_url": SecretStr(reader),
    }))
    verifier.jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key()),
    )
    token = jwt.encode({
        "iss": verifier.issuer, "aud": "authenticated", "role": "authenticated",
        "sub": str(user_id), "session_id": str(session_id), "email": "identity@example.test",
        "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(minutes=5),
        "auth_time": datetime.now(UTC).timestamp(),
    }, key, algorithm="RS256")
    return verifier, token


@pytest.mark.parametrize("age,allowed", [(11, False), (9, True), (-1, False)])
def test_real_readonly_session_creation_is_reauthentication_not_refresh_or_new_jwt(
    postgres, tmp_path, age, allowed
):
    stamp = datetime.now(UTC) - timedelta(minutes=age)
    reader, user_id, session_id = auth_session(postgres, created_at=stamp)
    verifier, token = signed_verifier(auth_settings(tmp_path), reader, user_id, session_id)
    try:
        identity = verifier.verify(token)
        if allowed:
            assert verifier.reauthenticated_at(identity) == stamp
        else:
            with pytest.raises(HTTPException) as error:
                verifier.reauthenticated_at(identity)
            assert error.value.status_code == 403
            assert error.value.detail["code"] == "REAUTH_REQUIRED"
        with psycopg.connect(reader, autocommit=True) as connection:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("SELECT encrypted_password FROM auth.users")
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                connection.execute("DELETE FROM auth.sessions WHERE id = %s", (session_id,))
    finally:
        verifier.engine.dispose()


def test_local_deactivation_keeps_identity_provider_account_and_readonly_session(client, postgres):
    state = client.app.state
    reader, user_id, session_id = auth_session(postgres, created_at=datetime.now(UTC))
    verifier, token = signed_verifier(state.settings, reader, user_id, session_id)
    state.auth_verifier = verifier
    headers = {**HEADERS, "Authorization": "Bearer " + token}
    try:
        owner = client.get("/me", headers=headers).json()["id"]
        assert request_deletion(client, headers=headers).status_code == 202
        assert process_account_deletions(state.session_factory, state.storage, state.settings) == 1
        assert process_account_deletions(state.session_factory, state.storage, state.settings) == 1
        progress = client.get("/me", headers=headers)
        assert progress.status_code == 200 and progress.json()["deletion"]["status"] == "completed"
        assert client.get("/billing/me", headers=headers).status_code == 403
        with state.session_factory() as session:
            assert session.get(User, owner).active is False
            assert session.get(User, owner).email is None
            mapping = session.scalar(select(AuthIdentity).where(AuthIdentity.user_id == owner))
            assert mapping.subject == str(user_id)
        with psycopg.connect(postgres[0], autocommit=True) as connection:
            assert connection.execute(
                "SELECT count(*) FROM auth.users WHERE id = %s", (user_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM auth.sessions WHERE id = %s", (session_id,),
            ).fetchone()[0] == 1
    finally:
        verifier.engine.dispose()
