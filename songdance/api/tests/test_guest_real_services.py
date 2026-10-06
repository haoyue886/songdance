"""Guest admissions and settlement against disposable, migrated PostgreSQL."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.models import GuestDay, GuestLedger, GuestSubmission, GuestTrial, TranscriptionJob
from app.services.usage import settle_job_in_factory
from tests.test_auth_real_services import postgres as postgres
from tests.test_dispatch_real_services import client as client
from tests.test_dispatch_real_services import database as database
from tests.test_guest_usage import access, counters, fail, submit, visitor

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)


@pytest.fixture
def guest_client(client):
    client.app.state.settings.guest_usage_enabled = True
    client.app.state.settings.guest_signing_secret = SecretStr(
        "guest-test-secret-at-least-thirty-two-characters"
    )
    return client


@pytest.mark.parametrize(
    "identity,key", [("same", "same"), ("same", "different"), ("different", "same")]
)
def test_concurrent_create_has_one_job_reservation_and_ip_admission(guest_client, identity, key):
    client = guest_client
    first = visitor(client).json()["visitor_token"]
    second = first if identity == "same" else visitor(client).json()["visitor_token"]
    barrier = Barrier(2)

    def create(index):
        barrier.wait(timeout=10)
        return submit(
            client,
            [first, second][index],
            key=f"concurrent-key-{index if key == 'different' else 0}",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(create, range(2)))
    if identity == key == "same":
        assert [response.status_code for response in responses] == [201, 201]
        assert responses[0].json()["id"] == responses[1].json()["id"]
        assert (
            responses[0].json()["guest_access_token"] == responses[1].json()["guest_access_token"]
        )
    else:
        assert sorted(response.status_code for response in responses) == [201, 429]
        rejected = next(response for response in responses if response.status_code == 429)
        expected = "GUEST_TRIAL_ACTIVE" if identity == "same" else "GUEST_DAILY_LIMIT"
        assert rejected.json()["detail"]["code"] == expected
    with client.app.state.session_factory() as session:
        for model in (TranscriptionJob, GuestLedger, GuestDay, GuestSubmission):
            assert len(session.scalars(select(model)).all()) == 1
        trials = session.scalars(select(GuestTrial)).all()
        assert sum(trial.reserved for trial in trials) == 1
        assert sum(trial.consumed for trial in trials) == 0
    assert len(client.app.state.job_queue.calls) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_failed_retry_reserves_only_one_attempt(guest_client, same_key):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    fail(client, job)
    barrier = Barrier(2)

    def retry(index):
        barrier.wait(timeout=10)
        return client.post(
            f"/jobs/{job['id']}/retry",
            headers=access(job, f"retry-key-{0 if same_key else index}"),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(retry, range(2)))
    assert sorted(response.status_code for response in responses) == (
        [200, 200] if same_key else [200, 409]
    )
    assert all(
        response.json()["attempt_count"] == 2
        for response in responses
        if response.status_code == 200
    )
    assert counters(client, token) == (1, 0)
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(GuestDay)).all()) == 1
        assert len(session.scalars(select(GuestLedger)).all()) == 3
        assert len(session.scalars(select(GuestSubmission)).all()) == 2
    assert client.app.state.job_queue.calls == [(job["id"], 1), (job["id"], 2)]


@pytest.mark.parametrize("successes", [(True, True), (False, False), (True, False)])
def test_concurrent_settlement_has_one_immutable_terminal_event(guest_client, successes):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    barrier = Barrier(2)

    def settle(success):
        barrier.wait(timeout=10)
        return settle_job_in_factory(client.app.state.session_factory, job["id"], success=success)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(settle, successes))
    assert sorted(results) == [False, True]
    with client.app.state.session_factory() as session:
        events = session.scalars(select(GuestLedger.event_type)).all()
        assert len(events) == 2 and events.count("reservation") == 1
        assert counters(client, token) == (0, int("consume" in events))


def test_concurrent_claim_has_one_owner_and_preserves_guest_entitlement(guest_client):
    client = guest_client
    token = visitor(client).json()["visitor_token"]
    job = submit(client, token).json()
    barrier = Barrier(2)

    def claim(who):
        barrier.wait(timeout=10)
        return client.post(
            f"/jobs/{job['id']}/claim",
            headers={**access(job), "Authorization": f"Bearer {who}"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(claim, ["alice", "bob"]))
    assert sorted(response.status_code for response in responses) == [200, 404]
    assert counters(client, token) == (1, 0)
    assert submit(client, token).status_code == 410
    with client.app.state.session_factory() as session:
        persisted = session.get(TranscriptionJob, job["id"])
        assert persisted.owner_user_id and persisted.guest_trial_id
        assert persisted.guest_secret_hash is None and persisted.usage_reservation_id is None


def test_same_key_waits_for_upload_before_default_capacity_check(guest_client, monkeypatch):
    import asyncio

    import app.routes.jobs as routes

    client = guest_client
    client.app.state.settings.client_active_job_limit = 1
    token = visitor(client).json()["visitor_token"]
    entered, release, second_started = Event(), Event(), Event()
    original = routes._write_upload

    async def held_upload(*args):
        if not entered.is_set():
            entered.set()
            assert await asyncio.to_thread(release.wait, 10)
        return await original(*args)

    monkeypatch.setattr(routes, "_write_upload", held_upload)

    def create(second=False):
        with TestClient(client.app) as peer:
            if second:
                second_started.set()
            return submit(peer, token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create)
        assert entered.wait(10)
        second = pool.submit(create, True)
        try:
            assert second_started.wait(10)
        finally:
            release.set()
        responses = [first.result(15), second.result(15)]
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()["id"] == responses[1].json()["id"]
    assert client.app.state.job_queue.calls == [(responses[0].json()["id"], 1)]
