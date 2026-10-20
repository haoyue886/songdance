"""Two paid periods, another paid owner and recoverable deletion on disposable PG.

All payment/identity objects are explicit offline fixtures. No existing database,
provider account, real payment or music-quality claim is involved.
"""

import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
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
    JobStatus,
    PaidPeriod,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
    User,
)
from app.services.auth import VerifiedIdentity
from app.services.creem_client import CreemError
from app.services.usage import reserve_period, settle_job
from tests.test_account_deletion import create_job, process, request_deletion
from tests.test_account_deletion_real_services import client as client
from tests.test_auth_real_services import postgres as postgres
from tests.test_billing_recovery import renewal
from tests.test_creem_billing import HEADERS, FakeProvider, event, pay
from tests.test_creem_billing import process as process_billing
from tests.test_creem_real_services import database as database

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; no real provider or existing database is used",
)


class OtherCustomer(FakeProvider):
    def __init__(self):
        super().__init__()
        self.subscription.update(
            id="sub_other", customer="cust_other", last_transaction_id="tx_other",
        )
        transaction = self.transactions.pop("tx_test")
        transaction.update(id="tx_other", subscription="sub_other", customer="cust_other")
        self.transactions["tx_other"] = transaction

    def create_checkout(self, **kwargs):
        super().create_checkout(**kwargs)
        self.checkout.update(id="ch_other", customer="cust_other", subscription="sub_other")
        return deepcopy(self.checkout)

    def get_checkout(self, checkout_id):
        assert checkout_id == "ch_other"
        return deepcopy(self.checkout)

    def get_subscription(self, subscription_id):
        assert subscription_id == "sub_other"
        return deepcopy(self.subscription)

    def cancel_subscription(self, subscription_id):
        raise AssertionError("Deletion must never cancel the other owner's subscription")


def snapshot_owner(factory, owner):
    models = (
        User, AuthIdentity, BillingAccount, CheckoutSession, BillingSubscription,
        PaidPeriod, UsagePeriod, UsageLedger, BillingCancellation, TranscriptionJob,
    )
    with factory() as session:
        return {
            model.__tablename__: [
                {attr.key: getattr(row, attr.key) for attr in model.__mapper__.column_attrs}
                for row in session.scalars(select(model).where(
                    model.id == owner if model is User else
                    model.owner_user_id == owner if model is TranscriptionJob else
                    model.user_id == owner
                ).order_by(model.id))
            ]
            for model in models
        }


def two_periods(client, provider):
    # The first synthetic invoice ends yesterday; the second is the current
    # adjoining period. This avoids overlapping historical invoice fixtures.
    end = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
    start = end - timedelta(days=30)
    provider.subscription.update(
        current_period_start_date=start.isoformat(), current_period_end_date=end.isoformat(),
        updated_at=start.isoformat(),
    )
    provider.transactions["tx_test"].update(
        period_start=int(start.timestamp() * 1000), period_end=int(end.timestamp() * 1000),
    )
    pay(client, provider)
    state = client.app.state
    owner = client.get("/me", headers=HEADERS).json()["id"]
    # Explicit historical task fixture; charge via the real reservation/settlement
    # functions, without pretending to run a historical model or HTTP clock.
    with state.session_factory.begin() as session:
        old = session.scalars(select(PaidPeriod).where(PaidPeriod.user_id == owner)).one()
        period = session.get(UsagePeriod, old.usage_period_id)
        job = TranscriptionJob(
            id=uuid4().hex, owner_user_id=owner, start_sec=0, end_sec=30,
            status=JobStatus.SUCCEEDED, expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(job)
        session.flush()
        job.usage_reservation_id = reserve_period(session, period, job.id, 30)
        assert settle_job(session, job, success=True, reason="offline_history_fixture")
        old_id, historical_job = old.id, job.id
    transaction = renewal(provider)
    assert event(client, "subscription.paid", "evt_second_period", {
        "id": "sub_test", "mode": "test", "last_transaction_id": transaction["id"],
    }).status_code == 200
    assert process_billing(client, provider) == 1
    with state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod).where(PaidPeriod.user_id == owner)).all()
        assert len(periods) == 2 and {p.status for p in periods} == {"active"}
        first = session.get(PaidPeriod, old_id)
        current = next(p for p in periods if p.id != old_id)
        assert first.period_end == current.period_start
        old_ledger = [
            (r.id, r.event_type, r.units, r.reservation_id)
            for r in session.scalars(select(UsageLedger).where(
                UsageLedger.period_id == first.usage_period_id
            ).order_by(UsageLedger.id))
        ]
    return owner, old_id, historical_job, old_ledger


@pytest.mark.parametrize("cancel_failure", ["before_mutation", "lost_response"])
def test_complete_paid_history_deletion_recovers_without_erasing_other_customer(
    client, monkeypatch, cancel_failure
):
    state, provider = client.app.state, client.app.state.creem_client
    owner, old_id, historical_job, old_ledger = two_periods(client, provider)
    target = create_job(client, "alice")
    assert target.status_code == 201
    job_id = target.json()["id"]
    source_key = f"jobs/{job_id}/source.wav"
    pipeline = state.settings.temp_path / f"pipeline-{job_id[:8]}-paid-delete"
    pipeline.mkdir()
    (pipeline / "source.wav").write_bytes(b"explicit offline pipeline fixture")

    other = OtherCustomer()
    state.creem_client = other
    bob_headers = {**HEADERS, "Authorization": "Bearer bob"}
    bob = client.get("/me", headers=bob_headers).json()["id"]
    checkout = client.post("/billing/checkout", headers={
        **bob_headers, "Idempotency-Key": "other_customer_checkout",
    }, json={})
    assert checkout.status_code == 200
    other.checkout["status"] = "completed"
    for kind, event_id, obj in (
        ("checkout.completed", "evt_other_checkout", {"id": "ch_other", "mode": "test"}),
        ("subscription.paid", "evt_other_paid", {
            "id": "sub_other", "mode": "test", "last_transaction_id": "tx_other",
        }),
    ):
        assert event(client, kind, event_id, obj).status_code == 200
        assert process_billing(client, other) == 1
    other_job = create_job(client, "bob")
    assert other_job.status_code == 201
    other_key = f"jobs/{other_job.json()['id']}/source.wav"
    other_bytes = (state.settings.local_storage_path / other_key).read_bytes()
    before_other = snapshot_owner(state.session_factory, bob)
    before_target = snapshot_owner(state.session_factory, owner)
    state.creem_client = provider
    original_cancel = provider.cancel_subscription
    calls = []

    def unavailable_or_lost_response(sub_id):
        calls.append(sub_id)
        if cancel_failure == "lost_response":
            original_cancel(sub_id)
        raise CreemError("offline cancellation failure")

    monkeypatch.setattr(provider, "cancel_subscription", unavailable_or_lost_response)
    accepted = request_deletion(client)
    assert accepted.status_code == 202
    deletion_id = accepted.json()["deletion"]["id"]
    now = datetime.now(UTC)
    assert process(client, provider, now=now) == 1
    with state.session_factory() as session:
        deletion = session.get(AccountDeletion, deletion_id)
        assert (deletion.phase, deletion.status) == ("billing", "retry")
        assert session.get(User, owner).active is True
        assert session.get(User, owner).email is not None
        assert session.get(TranscriptionJob, job_id) is not None
        assert session.get(TranscriptionJob, historical_job) is not None
    assert state.storage.exists(source_key) and pipeline.exists()
    assert create_job(client, "alice").status_code == 409
    assert snapshot_owner(state.session_factory, bob) == before_other

    monkeypatch.setattr(provider, "cancel_subscription", original_cancel)
    later = now + timedelta(hours=1)
    assert process(client, provider, now=later) == 1
    with state.session_factory() as session:
        deletion = session.get(AccountDeletion, deletion_id)
        assert (deletion.phase, deletion.status) == ("cleanup", "pending")
        assert session.get(User, owner).active is False
        assert session.get(TranscriptionJob, job_id) is not None
        step = session.scalars(select(AccountDeletionSubscription)).one()
        assert step.subscription_id == "sub_test" and step.status == "verified"
    assert state.storage.exists(source_key) and pipeline.exists()
    assert calls == ["sub_test"] and provider.cancel_calls == ["sub_test"]
    assert process(client, provider, now=later) == 1
    assert process(client, provider, now=later) == 0
    assert not state.storage.exists(source_key) and not pipeline.exists()
    assert (state.settings.local_storage_path / other_key).read_bytes() == other_bytes
    assert snapshot_owner(state.session_factory, bob) == before_other
    with state.session_factory() as session:
        assert session.get(AccountDeletion, deletion_id).status == "completed"
        assert session.get(User, owner).email is None
        assert session.scalar(select(TranscriptionJob.id).where(
            TranscriptionJob.owner_user_id == owner
        )) is None
        periods = session.scalars(select(PaidPeriod).where(PaidPeriod.user_id == owner)).all()
        assert len(periods) == 2 and {p.status for p in periods} == {"active"}
        first = session.get(PaidPeriod, old_id)
        previous = session.get(UsagePeriod, first.usage_period_id)
        assert (previous.consumed_units, previous.reserved_units) == (30, 0)
        remaining = next(p for p in periods if p.id != old_id)
        current = session.get(UsagePeriod, remaining.usage_period_id)
        assert (current.consumed_units, current.reserved_units) == (0, 0)
        assert [
            (r.id, r.event_type, r.units, r.reservation_id)
            for r in session.scalars(select(UsageLedger).where(
                UsageLedger.period_id == first.usage_period_id
            ).order_by(UsageLedger.id))
        ] == old_ledger
        assert sorted(session.scalars(select(UsageLedger.event_type).where(
            UsageLedger.period_id == current.id
        ))) == ["release", "reservation"]
        assert session.scalar(select(BillingCancellation.id)) is None
        assert all(
            row.status == "processed" for row in session.scalars(select(BillingWebhookEvent))
        )

    verify = state.auth_verifier.verify
    identity = verify("alice")
    monkeypatch.setattr(state.auth_verifier, "verify", lambda token: VerifiedIdentity(
        identity.issuer, identity.subject, "changed@example.test", identity.session_id,
    ) if token == "alice" else verify(token))
    account = client.get("/me", headers=HEADERS)
    assert account.status_code == 200 and account.json()["id"] == owner
    assert account.json()["email"] is None
    assert account.json()["deletion"]["status"] == "completed"
    assert create_job(client, "alice").status_code == 403
    with state.session_factory() as session:
        assert len(session.scalars(select(User)).all()) == 2
        assert len(session.scalars(select(AuthIdentity)).all()) == 2
        assert len(session.scalars(select(UsagePeriod)).all()) == 3
    assert snapshot_owner(state.session_factory, bob) == before_other
    final_target = snapshot_owner(state.session_factory, owner)
    for table in (
        "auth_identities", "billing_accounts", "checkout_sessions", "paid_periods",
        "billing_cancellations",
    ):
        assert final_target[table] == before_target[table], table
    assert other.cancel_calls == []
