"""Local account deactivation and cleanup; identity-provider accounts remain out of scope."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import (
    AccountDeletion,
    AccountDeletionSubscription,
    AuthIdentity,
    BillingAccount,
    BillingCancellation,
    BillingSubscription,
    BillingWebhookEvent,
    CheckoutSession,
    JobStage,
    JobStatus,
    PaidPeriod,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
    User,
)
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent
from app.services.account_deletion import process_account_deletions
from app.services.auth import VerifiedIdentity
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import reconcile_known
from app.services.creem_client import CreemError
from app.services.temp_cleanup import TempCleanupResult
from app.services.transcription_persistence import mark_failed, persist_result, set_stage
from app.services.usage import _as_utc, settle_job_in_factory
from app.settings import Settings
from tests.conftest import wav_bytes
from tests.test_creem_billing import HEADERS, FakeProvider, bind, event, pay
from tests.test_creem_billing import billing as billing
from tests.test_creem_billing import checkout as billing_checkout
from tests.test_creem_billing import process as process_billing
from tests.test_entitlements import grant


@pytest.fixture
def deletion_client(billing):
    client, provider = billing
    client.app.state.settings = Settings(_env_file=None, **{
        **client.app.state.settings.model_dump(),
        "account_deletion_enabled": True, "reliable_queue_enabled": True,
    })
    client.app.state.auth_verifier.reauthenticated_at = lambda identity: datetime.now(UTC)
    return client, provider


def create_job(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if client.app.state.settings.reliable_queue_enabled:
        headers["Idempotency-Key"] = uuid4().hex
    return client.post(
        "/jobs", headers=headers,
        files={"audio_file": ("sample.wav", wav_bytes(), "audio/wav")},
        data={"start_sec": "0", "end_sec": "2", "rights_confirmed": "true"},
    )


def request_deletion(client, *, headers=None, body=None):
    return client.request(
        "DELETE", "/me", headers=HEADERS if headers is None else headers,
        json={"confirmation": "DELETE"} if body is None else body,
    )


def process(client, provider, *, now=None):
    state = client.app.state
    return process_account_deletions(
        state.session_factory, state.storage, state.settings, provider, state.job_quota, now=now,
    )


def deletion_row(client):
    with client.app.state.session_factory() as session:
        return session.scalars(select(AccountDeletion)).one()


def page(items, *, number=1, total=None):
    total = len(items) if total is None else total
    pages = (total + 99) // 100
    return {
        "items": deepcopy(items),
        "pagination": {
            "total_records": total, "total_pages": pages, "current_page": number,
            "next_page": number + 1 if number < pages else None,
            "prev_page": number - 1 if number > 1 else None,
        },
    }


def test_default_flag_disables_new_requests_and_status_remains_private(billing):
    client, provider = billing
    assert Settings(_env_file=None).account_deletion_enabled is False
    summary = client.get("/me", headers=HEADERS)
    assert summary.status_code == 200 and summary.headers["cache-control"] == "private, no-store"
    assert summary.json()["account_deletion_enabled"] is False
    assert summary.json()["deletion"] is None
    response = request_deletion(client)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ACCOUNT_DELETION_DISABLED"
    status = client.get("/me/deletion", headers=HEADERS)
    assert status.json() == {"enabled": False, "deletion": None}
    assert status.headers["cache-control"] == "private, no-store"
    assert client.get("/me/deletion").status_code == 401
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletion)) is None
    assert provider.cancel_calls == []


@pytest.mark.parametrize("headers,code", [
    ({"Origin": HEADERS["Origin"]}, 401),
    ({**HEADERS, "Authorization": "Bearer forged"}, 401),
    ({"Authorization": HEADERS["Authorization"]}, 403),
    ({**HEADERS, "Origin": "https://evil.test"}, 403),
])
def test_delete_requires_authenticated_identity_and_allowed_origin(deletion_client, headers, code):
    client, _ = deletion_client
    assert request_deletion(client, headers=headers).status_code == code
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletion)) is None


@pytest.mark.parametrize("body", [
    {}, {"confirmation": "delete"}, {"confirmation": True},
    {"confirmation": "DELETE", "user_id": "someone-else"},
])
def test_delete_requires_explicit_confirmation_and_rejects_browser_owner(deletion_client, body):
    client, _ = deletion_client
    assert request_deletion(client, body=body).status_code == 422
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletion)) is None


@pytest.mark.parametrize("age", [None, timedelta(minutes=11), timedelta(minutes=-1)])
def test_new_request_rejects_missing_expired_and_future_reauthentication(
    deletion_client, monkeypatch, age
):
    client, _ = deletion_client
    stamp = None if age is None else datetime.now(UTC) - age
    monkeypatch.setattr(
        client.app.state.auth_verifier, "reauthenticated_at", lambda identity: stamp,
    )
    response = request_deletion(client)
    assert response.status_code == 403 and response.json()["detail"]["code"] == "REAUTH_REQUIRED"
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletion)) is None
        assert session.scalar(select(User.active)) is True


def test_missing_reauthentication_capability_fails_closed(deletion_client, monkeypatch):
    client, _ = deletion_client
    monkeypatch.delattr(client.app.state.auth_verifier, "reauthenticated_at")
    response = request_deletion(client)
    assert response.status_code == 403 and response.json()["detail"]["code"] == "REAUTH_REQUIRED"


def test_reauthentication_service_unavailable_does_not_create_request_or_mutate_data(
    deletion_client, monkeypatch
):
    client, provider = deletion_client
    job = create_job(client, "alice").json()

    def unavailable(identity):
        raise HTTPException(503, detail={"code": "AUTH_UNAVAILABLE"})

    monkeypatch.setattr(client.app.state.auth_verifier, "reauthenticated_at", unavailable)
    response = request_deletion(client)
    assert response.status_code == 503 and response.json()["detail"]["code"] == "AUTH_UNAVAILABLE"
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletion)) is None
        assert session.get(TranscriptionJob, job["id"]) is not None
        assert session.scalar(select(User.active)) is True
    assert provider.cancel_calls == []


def test_request_is_per_user_idempotent_without_resetting_retry_history(
    deletion_client, monkeypatch
):
    client, _ = deletion_client
    first = request_deletion(client)
    assert first.status_code == 202 and first.headers["cache-control"] == "private, no-store"
    accepted = first.json()["deletion"]
    assert (accepted["status"], accepted["phase"], accepted["attempts"]) == (
        "pending", "billing", 0,
    )
    now = datetime.now(UTC) + timedelta(hours=1)
    with client.app.state.session_factory.begin() as session:
        row = session.get(AccountDeletion, accepted["id"])
        row.status, row.attempts, row.error_code = "retry", 4, "DELETION_BILLING_RETRY"
        row.retry_failures = 4
        row.next_attempt_at = now
        confirmed = row.auth_confirmed_at

    def should_not_reauthenticate(identity):
        raise AssertionError("Idempotent progress reads must not reset the request")

    monkeypatch.setattr(
        client.app.state.auth_verifier, "reauthenticated_at", should_not_reauthenticate,
    )
    duplicate = request_deletion(client)
    assert duplicate.status_code == 202
    assert duplicate.json()["deletion"]["id"] == accepted["id"]
    row = deletion_row(client)
    assert (row.status, row.attempts, row.error_code) == ("retry", 4, "DELETION_BILLING_RETRY")
    assert row.retry_failures == 4
    assert _as_utc(row.next_attempt_at) == now and row.auth_confirmed_at == confirmed
    assert client.get("/me", headers=HEADERS).json()["deletion"]["id"] == accepted["id"]
    other = client.get("/me/deletion", headers={"Authorization": "Bearer bob"}).json()
    assert other == {"enabled": True, "deletion": None}


def test_review_requires_fresh_identity_and_keeps_cumulative_attempts(deletion_client, monkeypatch):
    client, _ = deletion_client
    identifier = request_deletion(client).json()["deletion"]["id"]
    with client.app.state.session_factory.begin() as session:
        row = session.get(AccountDeletion, identifier)
        row.status, row.attempts, row.error_code = "review", 8, "DELETION_BILLING_RETRY"
        row.retry_failures = 8
    monkeypatch.setattr(
        client.app.state.auth_verifier, "reauthenticated_at",
        lambda identity: datetime.now(UTC) - timedelta(minutes=11),
    )
    assert request_deletion(client).status_code == 403
    assert deletion_row(client).status == "review"
    assert deletion_row(client).retry_failures == 8
    monkeypatch.setattr(
        client.app.state.auth_verifier, "reauthenticated_at", lambda identity: datetime.now(UTC),
    )
    response = request_deletion(client)
    assert response.status_code == 202
    assert response.json()["deletion"]["id"] == identifier
    assert (deletion_row(client).status, deletion_row(client).attempts) == ("pending", 8)
    assert deletion_row(client).retry_failures == 0


def test_pending_request_blocks_jobs_retries_checkouts_and_claims(deletion_client):
    client, provider = deletion_client
    owned = create_job(client, "alice").json()
    guest = create_job(client).json()
    mark_failed(
        client.app.state.session_factory, owned["id"], "FAILED", "offline", expected_attempt=1,
    )
    assert request_deletion(client).status_code == 202
    responses = [
        create_job(client, "alice"),
        client.post(f"/jobs/{owned['id']}/retry", headers=HEADERS),
        billing_checkout(client),
        client.post(f"/jobs/{guest['id']}/claim", headers={
            **HEADERS, "X-Job-Access": guest["guest_access_token"],
        }),
    ]
    assert [response.status_code for response in responses] == [409] * 4
    assert all(
        response.json()["detail"]["code"] == "ACCOUNT_DELETION_PENDING" for response in responses
    )
    assert provider.create_calls == []
    with client.app.state.session_factory() as session:
        assert session.get(TranscriptionJob, guest["id"]).owner_user_id is None
        assert session.get(TranscriptionJob, owned["id"]).attempt_count == 1


def test_stopped_billing_checkpoint_precedes_cleanup_and_preserves_necessary_history(
    deletion_client
):
    client, provider = deletion_client
    pay(client, provider)
    owner = client.get("/me", headers=HEADERS).json()["id"]
    job = create_job(client, "alice").json()
    guest = create_job(client).json()
    state = client.app.state
    source_key = f"jobs/{job['id']}/source.wav"
    pipeline = state.settings.temp_path / f"pipeline-{job['id'][:8]}-cleanup"
    pipeline.mkdir()
    (pipeline / "audio.wav").write_bytes(b"temporary audio")
    identifier = request_deletion(client).json()["deletion"]["id"]
    assert process(client, provider) == 1
    with state.session_factory() as session:
        user = session.get(User, owner)
        row = session.get(AccountDeletion, identifier)
        assert (row.phase, row.status, row.attempts) == ("cleanup", "pending", 1)
        assert user.active is False and user.email == "same@example.test"
        assert session.get(TranscriptionJob, job["id"]) is not None
        assert session.scalar(select(UsagePeriod.reserved_units)) == 15
        step = session.scalars(select(AccountDeletionSubscription)).one()
        assert step.status == "verified" and step.verified_at is not None
    assert provider.cancel_calls == ["sub_test"]
    assert state.storage.exists(source_key) and pipeline.exists()
    assert client.get("/me/deletion", headers=HEADERS).status_code == 200
    assert client.get("/billing/me", headers=HEADERS).status_code == 403
    assert create_job(client, "alice").status_code == 403
    assert process(client, provider) == 1
    assert not state.storage.exists(source_key) and not pipeline.exists()
    with state.session_factory() as session:
        user = session.get(User, owner)
        row = session.get(AccountDeletion, identifier)
        assert user.active is False and user.email is None
        assert (row.status, row.phase, row.attempts) == ("completed", "cleanup", 2)
        assert row.completed_at is not None
        assert session.get(TranscriptionJob, job["id"]) is None
        assert session.get(TranscriptionJob, guest["id"]) is not None
        assert session.scalars(select(AuthIdentity)).one().user_id == owner
        assert session.scalars(select(BillingAccount)).one().customer_id == "cust_alice"
        assert session.scalars(select(BillingSubscription)).one().status == "canceled"
        assert session.scalars(select(CheckoutSession)).one().status == "completed"
        assert len(session.scalars(select(BillingWebhookEvent)).all()) == 2
        assert session.scalars(select(PaidPeriod)).one().status == "active"
        assert sorted(session.scalars(select(UsageLedger.event_type)).all()) == [
            "release", "reservation",
        ]
        period = session.scalars(select(UsagePeriod)).one()
        assert (period.reserved_units, period.consumed_units) == (0, 0)
    assert process(client, provider) == 0
    assert request_deletion(client).json()["deletion"]["id"] == identifier


def test_cleanup_uses_batches_and_disabling_flag_does_not_abandon_accepted_work(deletion_client):
    client, _ = deletion_client
    owner = client.get("/me", headers=HEADERS).json()["id"]
    state = client.app.state
    state.settings.cleanup_batch_size = 1
    with state.session_factory.begin() as session:
        session.add_all([
            TranscriptionJob(
                id=f"owned-{number}", owner_user_id=owner, start_sec=0, end_sec=2,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            for number in range(3)
        ])
    assert request_deletion(client).status_code == 202
    state.settings.account_deletion_enabled = False
    assert process(client, None) == 1
    for remaining in (2, 1, 0):
        assert process(client, None) == 1
        with state.session_factory() as session:
            assert len(session.scalars(select(TranscriptionJob)).all()) == remaining
            assert session.get(User, owner).email == ("same@example.test" if remaining else None)
        assert deletion_row(client).status == ("pending" if remaining else "completed")
    assert client.get("/me/deletion", headers=HEADERS).json()["enabled"] is False


@pytest.mark.parametrize("provider_id", [False, True])
def test_unresolved_checkout_retries_without_clearing_account_or_files(
    deletion_client, provider_id
):
    client, provider = deletion_client
    job = create_job(client, "alice").json()
    assert billing_checkout(client).status_code == 200
    if not provider_id:
        with client.app.state.session_factory.begin() as session:
            session.scalar(select(CheckoutSession)).provider_id = None
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    row = deletion_row(client)
    assert (row.status, row.phase, row.attempts) == ("retry", "billing", 1)
    assert row.error_code == "DELETION_BILLING_RETRY"
    with client.app.state.session_factory() as session:
        assert session.get(User, row.user_id).active is True
        assert session.get(User, row.user_id).email == "same@example.test"
        assert session.get(TranscriptionJob, job["id"]) is not None
    assert client.app.state.storage.exists(f"jobs/{job['id']}/source.wav")
    assert provider.cancel_calls == []


def test_checkout_completed_after_request_is_bound_and_canceled_before_cleanup(deletion_client):
    client, provider = deletion_client
    assert billing_checkout(client).status_code == 200
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1 and deletion_row(client).status == "retry"
    provider.checkout["status"] = "completed"
    assert process(client, provider, now=datetime.now(UTC) + timedelta(hours=1)) == 1
    assert deletion_row(client).phase == "cleanup"
    assert provider.cancel_calls == ["sub_test"]
    with client.app.state.session_factory() as session:
        assert session.scalars(select(BillingSubscription)).one().user_id == (
            deletion_row(client).user_id
        )


def test_provider_outage_stays_durable_and_moves_to_review_on_eighth_failure(
    deletion_client, monkeypatch
):
    client, provider = deletion_client
    bind(client, provider)

    def unavailable(*args, **kwargs):
        raise CreemError("offline provider secret must not reach progress")

    monkeypatch.setattr(provider, "list_customer_subscriptions", unavailable)
    assert request_deletion(client).status_code == 202
    start = datetime.now(UTC)
    for attempt in range(1, 9):
        assert process(client, provider, now=start + timedelta(days=attempt)) == 1
        row = deletion_row(client)
        assert row.attempts == attempt
        assert row.retry_failures == attempt
        assert row.status == ("retry" if attempt < 8 else "review")
        assert row.error_code == "DELETION_BILLING_RETRY"
    assert process(client, provider, now=start + timedelta(days=10)) == 0
    assert "offline provider secret" not in client.get("/me/deletion", headers=HEADERS).text
    assert request_deletion(client).status_code == 202
    assert deletion_row(client).attempts == 8
    assert process(client, provider, now=start + timedelta(days=11)) == 1
    assert (deletion_row(client).attempts, deletion_row(client).status) == (9, "retry")
    assert deletion_row(client).retry_failures == 1


@pytest.mark.parametrize("status", ["canceled", "scheduled_cancel"])
def test_provider_already_stopped_subscription_is_verified_without_new_cancel(
    deletion_client, status
):
    client, provider = deletion_client
    bind(client, provider)
    provider.subscription.update(status=status, updated_at=datetime.now(UTC).isoformat())
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    assert deletion_row(client).phase == "cleanup" and provider.cancel_calls == []


def test_cancel_response_alone_does_not_confirm_billing_stopped(deletion_client, monkeypatch):
    client, provider = deletion_client
    bind(client, provider)

    def response_without_mutation(sub_id):
        provider.cancel_calls.append(sub_id)
        return {**provider.subscription, "status": "canceled"}

    monkeypatch.setattr(provider, "cancel_subscription", response_without_mutation)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    row = deletion_row(client)
    assert (row.status, row.phase) == ("retry", "billing")
    with client.app.state.session_factory() as session:
        assert session.get(User, row.user_id).active is True
        assert session.scalar(select(AccountDeletionSubscription)) is None


def test_cancel_timeout_recovers_from_get_without_duplicate_mutation(deletion_client, monkeypatch):
    client, provider = deletion_client
    bind(client, provider)
    cancel = provider.cancel_subscription

    def unknown_outcome(sub_id):
        cancel(sub_id)
        raise CreemError("cancellation response lost")

    monkeypatch.setattr(provider, "cancel_subscription", unknown_outcome)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1 and deletion_row(client).status == "retry"
    assert process(client, provider, now=datetime.now(UTC) + timedelta(hours=1)) == 1
    assert deletion_row(client).phase == "cleanup" and provider.cancel_calls == ["sub_test"]


@pytest.mark.parametrize("kind,expected", [
    ("missing", "DELETION_SUBSCRIPTION_MISSING"),
    ("unbound", "DELETION_UNBOUND_SUBSCRIPTION"),
    ("customer", "DELETION_UNBOUND_SUBSCRIPTION"),
    ("duplicate", "DELETION_SUBSCRIPTION_REPEATED"),
    ("live", "DELETION_BILLING_REVIEW"),
    ("invalid_pagination", "DELETION_BILLING_REVIEW"),
])
def test_unverified_customer_enumeration_enters_review_before_any_cancel(
    deletion_client, monkeypatch, kind, expected
):
    client, provider = deletion_client
    bind(client, provider)
    remote = deepcopy(provider.subscription)
    if kind == "missing":
        listing = page([])
    elif kind == "unbound":
        listing = page([remote, {**remote, "id": "unbound-subscription"}])
    elif kind == "customer":
        listing = page([{**remote, "customer": "cust_bob"}])
    elif kind == "duplicate":
        listing = page([remote, remote])
    elif kind == "live":
        listing = page([{**remote, "mode": "prod"}])
    else:
        listing = page([remote], total=101)
    monkeypatch.setattr(provider, "list_customer_subscriptions", lambda *args, **kwargs: listing)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    row = deletion_row(client)
    assert (row.status, row.phase, row.error_code) == ("review", "billing", expected)
    assert provider.cancel_calls == []
    with client.app.state.session_factory() as session:
        assert session.get(User, row.user_id).active is True


@pytest.mark.parametrize("kind,expected", [
    ("live", "DELETION_UNVERIFIED_ENVIRONMENT"),
    ("customer", "DELETION_CUSTOMER_CONFLICT"),
    ("paid_without_binding", "DELETION_UNBOUND_PAYMENT"),
    ("stale", "DELETION_STALE_SUBSCRIPTION"),
])
def test_unverified_local_obligation_blocks_cleanup(deletion_client, kind, expected):
    client, provider = deletion_client
    owner = client.get("/me", headers=HEADERS).json()["id"]
    if kind == "paid_without_binding":
        with client.app.state.session_factory.begin() as session:
            grant(session, owner)
    else:
        bind(client, provider)
        if kind in {"live", "customer"}:
            with client.app.state.session_factory.begin() as session:
                account = session.scalar(select(BillingAccount))
                if kind == "live":
                    account.environment = "live"
                else:
                    account.customer_id = "cust_bob"
        else:
            stale = datetime.now(UTC) - timedelta(days=2)
            provider.subscription["updated_at"] = stale.isoformat()
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    row = deletion_row(client)
    assert (row.status, row.error_code) == ("review", expected)
    assert provider.cancel_calls == []


class ManySubscriptions(FakeProvider):
    def __init__(self):
        super().__init__()
        self.subscriptions = {
            "sub_test": self.subscription,
            **{
                f"sub_{number}": {**self.subscription, "id": f"sub_{number}"}
                for number in range(100)
            },
        }

    def get_subscription(self, sub_id):
        return deepcopy(self.subscriptions[sub_id])

    def cancel_subscription(self, sub_id):
        self.cancel_calls.append(sub_id)
        self.subscriptions[sub_id].update(
            status="canceled", updated_at=datetime.now(UTC).isoformat(),
        )
        return self.get_subscription(sub_id)

    def list_customer_subscriptions(self, customer_id, *, page_number=1, page_size=100):
        self.subscription_list_calls.append((customer_id, page_number, page_size))
        items = list(self.subscriptions.values())
        start = (page_number - 1) * page_size
        return page(items[start : start + page_size], number=page_number, total=len(items))


@pytest.fixture
def many_subscriptions(deletion_client):
    client, _ = deletion_client
    provider = ManySubscriptions()
    client.app.state.creem_client = provider
    bind(client, provider)
    with client.app.state.session_factory.begin() as session:
        original = session.scalars(select(BillingSubscription)).one()
        session.add_all([
            BillingSubscription(
                id=uuid4().hex, user_id=original.user_id, environment="test", provider_id=sub_id,
                customer_id=original.customer_id, checkout_id=original.checkout_id, status="active",
                provider_updated_at=original.provider_updated_at,
            )
            for sub_id in provider.subscriptions if sub_id != "sub_test"
        ])
    return client, provider


def test_all_customer_pages_are_bound_and_verified_before_cleanup(many_subscriptions):
    client, provider = many_subscriptions
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    assert deletion_row(client).phase == "cleanup"
    assert provider.subscription_list_calls == [("cust_alice", 1, 100), ("cust_alice", 2, 100)]
    assert set(provider.cancel_calls) == set(provider.subscriptions)
    with client.app.state.session_factory() as session:
        steps = session.scalars(select(AccountDeletionSubscription)).all()
        assert len(steps) == 101 and all(step.status == "verified" for step in steps)


@pytest.mark.parametrize("change,expected", [
    ("repeated", "review"), ("total_changed", "retry"),
])
def test_later_customer_page_changes_block_any_cancellation(
    many_subscriptions, monkeypatch, change, expected
):
    client, provider = many_subscriptions
    original = provider.list_customer_subscriptions

    def changed(customer_id, **pagination):
        listing = original(customer_id, **pagination)
        if pagination["page_number"] == 2:
            if change == "repeated":
                listing["items"][0] = deepcopy(provider.subscription)
            else:
                listing["pagination"]["total_records"] = 102
                listing["items"].append({**provider.subscription, "id": "new-subscription"})
        return listing

    monkeypatch.setattr(provider, "list_customer_subscriptions", changed)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    assert deletion_row(client).status == expected
    assert deletion_row(client).phase == "billing" and provider.cancel_calls == []
    with client.app.state.session_factory() as session:
        assert session.scalar(select(AccountDeletionSubscription)) is None
        assert session.scalar(select(User.active)) is True


@pytest.mark.parametrize("failure", ["object_storage", "temporary_files"])
def test_cleanup_failure_persists_release_and_fence_against_late_worker(
    deletion_client, monkeypatch, failure
):
    import app.services.account_deletion as deletion_service

    client, provider = deletion_client
    job = create_job(client, "alice").json()
    state = client.app.state
    with state.session_factory() as session:
        reservation = session.get(TranscriptionJob, job["id"]).usage_reservation_id
    assert request_deletion(client).status_code == 202 and process(client, provider) == 1
    original_delete = state.storage.delete
    original_temp_cleanup = deletion_service.cleanup_job_temp_files

    def unavailable(key):
        raise OSError("isolated storage failure")

    if failure == "object_storage":
        monkeypatch.setattr(state.storage, "delete", unavailable)
    else:
        monkeypatch.setattr(
            deletion_service, "cleanup_job_temp_files", lambda *args: TempCleanupResult(0, 1),
        )
    assert process(client, provider) == 1
    assert (deletion_row(client).status, deletion_row(client).error_code) == (
        "retry", "DELETION_CLEANUP_RETRY",
    )
    with state.session_factory() as session:
        retained = session.get(TranscriptionJob, job["id"])
        assert (retained.status, retained.error_code) == ("failed", "DELETE_FAILED")
        period = session.scalars(select(UsagePeriod)).one()
        assert (period.reserved_units, period.consumed_units) == (0, 0)
        assert session.scalar(select(User.email)) == "same@example.test"
    assert not set_stage(
        state.session_factory, job["id"], JobStatus.RUNNING, JobStage.SCORE, expected_attempt=1,
    )
    mark_failed(state.session_factory, job["id"], "LATE_FAILURE", "late worker", expected_attempt=1)
    scored = build_score([NoteEvent(0, 1, 60, 100, 0.9)])
    assert not persist_result(
        state.session_factory, state.storage, job["id"], scored, [], expected_attempt=1,
    )
    assert not settle_job_in_factory(
        state.session_factory, job["id"], success=True, expected_attempt=1,
        reservation_id=reservation,
    )
    with state.session_factory() as session:
        assert session.get(TranscriptionJob, job["id"]).error_code == "DELETE_FAILED"
        assert sorted(session.scalars(select(UsageLedger.event_type)).all()) == [
            "release", "reservation",
        ]
    monkeypatch.setattr(state.storage, "delete", original_delete)
    monkeypatch.setattr(deletion_service, "cleanup_job_temp_files", original_temp_cleanup)
    assert process(client, provider, now=datetime.now(UTC) + timedelta(hours=1)) == 1
    assert deletion_row(client).status == "completed"


def test_same_identity_with_changed_email_cannot_recreate_account_or_free_credit(
    deletion_client, monkeypatch
):
    client, provider = deletion_client
    owner = client.get("/me", headers=HEADERS).json()["id"]
    assert create_job(client, "alice").status_code == 201
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1 and process(client, provider) == 1
    identity = client.app.state.auth_verifier.verify("alice")
    monkeypatch.setattr(client.app.state.auth_verifier, "verify", lambda token: VerifiedIdentity(
        identity.issuer, identity.subject, "different@example.test", identity.session_id,
    ))
    me = client.get("/me", headers=HEADERS)
    assert me.status_code == 200 and me.json()["id"] == owner and me.json()["email"] is None
    assert me.json()["deletion"]["status"] == "completed"
    assert create_job(client, "alice").status_code == 403
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(AuthIdentity)).all()) == 1
        assert len(session.scalars(select(UsagePeriod)).all()) == 1


def test_cleanup_retry_budget_preserves_fence_and_review_resumes_without_resetting_attempts(
    deletion_client, monkeypatch
):
    client, provider = deletion_client
    job = create_job(client, "alice").json()
    assert request_deletion(client).status_code == 202 and process(client, provider) == 1
    state = client.app.state
    original = state.storage.delete

    def unavailable(key):
        raise OSError("isolated cleanup failure")

    monkeypatch.setattr(state.storage, "delete", unavailable)
    start = datetime.now(UTC)
    for failure in range(1, 9):
        assert process(client, provider, now=start + timedelta(days=failure)) == 1
        row = deletion_row(client)
        assert row.attempts == failure + 1 and row.phase == "cleanup"
        assert row.retry_failures == failure
        assert row.status == ("retry" if failure < 8 else "review")
    with state.session_factory() as session:
        assert session.get(TranscriptionJob, job["id"]).error_code == "DELETE_FAILED"
        assert session.scalar(select(User.email)) == "same@example.test"
        assert session.scalars(select(UsageLedger.event_type)).all().count("release") == 1
    assert process(client, provider, now=start + timedelta(days=10)) == 0
    assert request_deletion(client).status_code == 202
    assert (deletion_row(client).phase, deletion_row(client).attempts) == ("cleanup", 9)
    assert deletion_row(client).retry_failures == 0
    monkeypatch.setattr(state.storage, "delete", original)
    assert process(client, provider, now=start + timedelta(days=11)) == 1
    assert (deletion_row(client).status, deletion_row(client).attempts) == ("completed", 10)
    assert deletion_row(client).retry_failures == 0


def test_successful_batches_do_not_spend_failure_budget_and_first_outage_auto_recovers(
    deletion_client, monkeypatch
):
    client, provider = deletion_client
    owner = client.get("/me", headers=HEADERS).json()["id"]
    state = client.app.state
    state.settings.cleanup_batch_size = 1
    with state.session_factory.begin() as session:
        session.add_all([
            TranscriptionJob(
                id=f"owned-{number:02d}", owner_user_id=owner, start_sec=0, end_sec=2,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            for number in range(10)
        ])
    assert request_deletion(client).status_code == 202 and process(client, provider) == 1
    for batch in range(1, 10):
        assert process(client, provider) == 1
        row = deletion_row(client)
        assert (row.attempts, row.retry_failures, row.status) == (batch + 1, 0, "pending")
    original = state.storage.delete

    def unavailable(key):
        raise OSError("first isolated storage outage after successful batches")

    monkeypatch.setattr(state.storage, "delete", unavailable)
    assert process(client, provider) == 1
    row = deletion_row(client)
    assert (row.attempts, row.retry_failures, row.status) == (11, 1, "retry")
    with state.session_factory() as session:
        remaining = session.scalars(select(TranscriptionJob)).one()
        assert remaining.id == "owned-09" and remaining.error_code == "DELETE_FAILED"
        assert session.get(User, owner).email == "same@example.test"
    monkeypatch.setattr(state.storage, "delete", original)
    assert process(client, provider) == 0
    assert process(client, provider, now=datetime.now(UTC) + timedelta(hours=1)) == 1
    row = deletion_row(client)
    assert (row.attempts, row.retry_failures, row.status) == (12, 0, "completed")


def test_cli_review_replay_resets_failure_budget_but_preserves_attempt_audit(
    deletion_client, monkeypatch
):
    import app.jobs.account_deletion as runner

    client, provider = deletion_client
    identifier = request_deletion(client).json()["deletion"]["id"]
    state = client.app.state
    with state.session_factory.begin() as session:
        row = session.get(AccountDeletion, identifier)
        row.status, row.attempts, row.retry_failures = "review", 20, 8
        row.error_code = "DELETION_BILLING_RETRY"
    settings = Settings(_env_file=None, **{
        **state.settings.model_dump(), "account_deletion_enabled": False,
    })
    monkeypatch.setattr(runner, "get_settings", lambda: settings)
    monkeypatch.setattr(runner, "create_storage", lambda settings: state.storage)
    monkeypatch.setattr(runner, "create_job_quota", lambda settings: state.job_quota)
    monkeypatch.setattr(runner, "CreemClient", lambda settings: provider)
    monkeypatch.setattr("sys.argv", ["account_deletion", "--once", f"--replay-id={identifier}"])
    observed = []

    def inspect_replay(factory, *args):
        with factory() as session:
            row = session.get(AccountDeletion, identifier)
            observed.append((row.status, row.attempts, row.retry_failures, row.error_code))
        return 0

    monkeypatch.setattr(runner, "process_account_deletions", inspect_replay)
    runner.main()
    assert observed == [("pending", 20, 0, None)]


def test_verified_billing_reactivation_reopens_checkpoint_without_reviving_user(deletion_client):
    client, provider = deletion_client
    pay(client, provider)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1 and process(client, provider) == 1
    original = deletion_row(client)
    provider.subscription.update(status="active", updated_at=datetime.now(UTC).isoformat())
    assert event(client, "subscription.active", "evt_reactivated").status_code == 200
    assert process_billing(client, provider) == 1
    row = deletion_row(client)
    assert row.id == original.id and row.completed_at is None
    assert (row.status, row.phase, row.error_code) == ("pending", "billing", "DELETION_NEW_BILLING")
    with client.app.state.session_factory() as session:
        assert session.get(User, row.user_id).active is False
        assert session.get(User, row.user_id).email is None
        assert session.scalar(select(BillingWebhookEvent).where(
            BillingWebhookEvent.event_id == "evt_reactivated"
        )).status == "processed"
    assert process(client, provider) == 1 and process(client, provider) == 1
    assert provider.cancel_calls == ["sub_test", "sub_test"]
    assert deletion_row(client).status == "completed"


@pytest.mark.parametrize("caller", ["webhook", "reconciliation", "refund_cancellation"])
@pytest.mark.parametrize("failure", ["unavailable", "contract_mismatch"])
def test_failed_financial_projection_still_persists_verified_reactivation_obligation(
    deletion_client, monkeypatch, caller, failure
):
    client, provider = deletion_client
    pay(client, provider)
    if caller == "refund_cancellation":
        provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
        assert event(client, "refund.created", "evt_refund_before_deletion", {
            "id": "refund_test", "mode": "test", "subscription": "sub_test",
            "transaction": "tx_test",
        }).status_code == 200
        assert process_billing(client, provider) == 1
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1 and process(client, provider) == 1
    original = deletion_row(client)
    provider.subscription.update(status="active", updated_at=datetime.now(UTC).isoformat())
    if failure == "unavailable":
        provider.fail_transaction = True
    else:
        provider.transactions["tx_test"].update(amount=991, amount_paid=991)
    if caller == "webhook":
        assert event(
            client, "subscription.paid", "evt_reactivated_bad_transaction",
        ).status_code == 200
        assert process_billing(client, provider) == 1
        with client.app.state.session_factory() as session:
            inbox = session.scalar(select(BillingWebhookEvent).where(
                BillingWebhookEvent.event_id == "evt_reactivated_bad_transaction"
            ))
            assert inbox.status == "retry"
    elif caller == "reconciliation":
        def unavailable_checkout(checkout_id):
            raise CreemError("offline checkout lookup")

        monkeypatch.setattr(provider, "get_checkout", unavailable_checkout)
        report = reconcile_known(client.app.state.session_factory, provider)
        assert report["completed"] == 0 and report["failed"] >= 2
    else:
        assert process_cancellations(client.app.state.session_factory, provider) == 1
        with client.app.state.session_factory() as session:
            assert session.scalar(select(BillingCancellation.status)) == "retry"
    row = deletion_row(client)
    assert row.id == original.id and row.completed_at is None
    assert (row.status, row.phase, row.error_code) == (
        "pending", "billing", "DELETION_NEW_BILLING",
    )
    assert row.attempts == original.attempts
    with client.app.state.session_factory() as session:
        assert session.get(User, row.user_id).active is False
        assert session.get(User, row.user_id).email is None
        assert len(session.scalars(select(PaidPeriod)).all()) == 1
