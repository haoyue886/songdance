"""Test-mode billing integration against isolated SQLite and an offline provider."""

import hashlib
import hmac
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.main import create_app
from app.models import (
    BillingAccount,
    BillingSubscription,
    BillingWebhookEvent,
    CheckoutSession,
    PaidPeriod,
    UsagePeriod,
)
from app.services.billing_events import process_pending
from app.services.creem_client import CreemError
from app.services.quota import MemoryJobQuota
from app.services.storage import LocalObjectStorage
from tests.conftest import RecordingQueue
from tests.test_auth_ownership import FakeVerifier, auth_settings

SECRET = "offline-webhook-secret-for-tests"
HEADERS = {"Authorization": "Bearer alice", "Origin": "http://localhost:3000"}


class FakeProvider:
    def __init__(self):
        self.product = {
            "id": "prod_test",
            "mode": "test",
            "price": 990,
            "currency": "USD",
            "billing_type": "recurring",
            "billing_period": "every-month",
        }
        start = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
        end = start + timedelta(days=30)
        self.subscription = {
            "id": "sub_test",
            "mode": "test",
            "customer": "cust_alice",
            "product": "prod_test",
            "status": "active",
            "updated_at": start.isoformat(),
            "current_period_start_date": start.isoformat(),
            "current_period_end_date": end.isoformat(),
            "last_transaction_id": "tx_test",
        }
        self.transactions = {
            "tx_test": {
                "id": "tx_test",
                "mode": "test",
                "subscription": "sub_test",
                "customer": "cust_alice",
                "type": "invoice",
                "status": "paid",
                "amount": 990,
                "amount_paid": 990,
                "currency": "USD",
                "period_start": int(start.timestamp() * 1000),
                "period_end": int(end.timestamp() * 1000),
            }
        }
        self.checkout = None
        self.create_calls = []
        self.portal_calls = []
        self.timeout = False
        self.fail_transaction = False

    def get_product(self, product_id):
        assert product_id == "prod_test"
        return deepcopy(self.product)

    def create_checkout(self, **kwargs):
        self.create_calls.append(kwargs)
        self.checkout = {
            "id": "ch_test",
            "mode": "test",
            "status": "pending",
            "request_id": kwargs["request_id"],
            "product": kwargs["product_id"],
            "checkout_url": "https://www.creem.io/test/checkout/ch_test",
            "customer": "cust_alice",
            "subscription": "sub_test",
            "units": 1,
        }
        if self.timeout:
            raise CreemError("unknown checkout outcome")
        return deepcopy(self.checkout)

    def get_checkout(self, checkout_id):
        assert checkout_id == "ch_test"
        return deepcopy(self.checkout)

    def get_subscription(self, subscription_id):
        assert subscription_id == "sub_test"
        return deepcopy(self.subscription)

    def get_transaction(self, transaction_id):
        if self.fail_transaction:
            raise CreemError("provider unavailable")
        return deepcopy(self.transactions[transaction_id])

    def create_portal(self, customer_id):
        self.portal_calls.append(customer_id)
        return {"customer_portal_link": "https://www.creem.io/test/portal"}


@pytest.fixture
def billing(tmp_path):
    settings = auth_settings(tmp_path).model_copy(
        update={
            "usage_enabled": True,
            "paid_usage_enabled": True,
            "creem_enabled": True,
            "billing_environment": "test",
            "creem_product_id": "prod_test",
            "creem_api_key": SecretStr("creem_test_offline"),
            "creem_webhook_secret": SecretStr(SECRET),
            "creem_success_url": "http://localhost:3000/billing/return",
        }
    )
    app = create_app(
        settings,
        storage=LocalObjectStorage(settings.local_storage_path),
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )
    original = app.state.auth_verifier
    app.state.auth_verifier = FakeVerifier({"alice": str(uuid4()), "bob": str(uuid4())})
    provider = FakeProvider()
    app.state.creem_client = provider
    with TestClient(app) as client:
        yield client, provider
    app.state.engine.dispose()
    original.engine.dispose()


def checkout(client, key="checkout_key_1", **body):
    return client.post("/billing/checkout", headers={**HEADERS, "Idempotency-Key": key}, json=body)


def event(client, kind, event_id, obj=None):
    if obj is None:
        obj = {"id": "sub_test", "mode": "test", "last_transaction_id": "tx_test"}
    raw = json.dumps({"id": event_id, "eventType": kind, "object": obj}).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/creem",
        content=raw,
        headers={"creem-signature": signature, "Content-Type": "application/json"},
    )


def process(client, provider):
    return process_pending(client.app.state.session_factory, provider)


def due(client):
    with client.app.state.session_factory() as session:
        for row in session.scalars(select(BillingWebhookEvent)):
            row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()


def bind(client, provider):
    response = checkout(client)
    assert response.status_code == 200
    provider.checkout["status"] = "completed"
    assert (
        event(
            client, "checkout.completed", "evt_checkout", {"id": "ch_test", "mode": "test"}
        ).status_code
        == 200
    )
    assert process(client, provider) == 1


def pay(client, provider):
    bind(client, provider)
    assert event(client, "subscription.paid", "evt_paid").status_code == 200
    assert process(client, provider) == 1


def test_durable_signed_event_grants_once_across_duplicate_events(billing):
    client, provider = billing
    bind(client, provider)
    assert event(client, "subscription.paid", "evt_paid").status_code == 200
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None
        inbox = session.scalar(
            select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == "evt_paid")
        )
        assert inbox.status == "pending" and inbox.attempts == 0
        intent = session.scalar(select(CheckoutSession))
        assert provider.create_calls[0]["request_id"] == intent.id
        assert intent.user_id == client.get("/me", headers=HEADERS).json()["id"]
    assert process(client, provider) == 1
    assert event(client, "subscription.paid", "evt_paid").status_code == 200
    assert event(client, "subscription.paid", "evt_paid_again").status_code == 200
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod)).all()
        assert len(periods) == 1 and periods[0].status == "active"
        usage = session.get(UsagePeriod, periods[0].usage_period_id)
        assert (usage.limit_units, usage.reserved_units, usage.consumed_units) == (1800, 0, 0)
        assert all(
            row.status == "processed" for row in session.scalars(select(BillingWebhookEvent))
        )


def test_paid_before_checkout_is_retried_after_binding(billing):
    client, provider = billing
    assert checkout(client).status_code == 200
    assert event(client, "subscription.paid", "evt_early").status_code == 200
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        row = session.scalar(select(BillingWebhookEvent))
        assert row.status == "retry" and row.attempts == 1
        assert session.scalar(select(PaidPeriod)) is None
    bind(client, provider)
    due(client)
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).transaction_id == "tx_test"


def test_invalid_signature_tampered_raw_body_and_live_mode_never_enter_inbox(billing):
    client, _ = billing
    raw = (
        b'{"id":"evt_bad","eventType":"subscription.paid","object":{"id":"sub_test","mode":"test"}}'
    )
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    for body, sig in ((raw + b" ", signature), (raw, "invalid"), (raw, "0" * 64)):
        assert (
            client.post(
                "/webhooks/creem", content=body, headers={"creem-signature": sig}
            ).status_code
            == 400
        )
    assert (
        event(
            client, "subscription.paid", "evt_live", {"id": "sub_test", "mode": "prod"}
        ).status_code
        == 400
    )
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None


@pytest.mark.parametrize("timeout", [False, True])
def test_open_or_uncertain_checkout_is_reused_without_duplicate_post(billing, timeout):
    client, provider = billing
    provider.timeout = timeout
    first = checkout(client)
    assert first.status_code == 200
    assert first.json()["status"] == ("uncertain" if timeout else "pending")
    assert checkout(client).json() == first.json()
    assert checkout(client, key="another_key_123").json() == first.json()
    assert len(provider.create_calls) == 1
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(CheckoutSession)).all()) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"user_id": "bob"},
        {"product_id": "prod_forged"},
        {"customer_id": "cust_bob"},
        {"success_url": "https://evil.test"},
    ],
)
def test_checkout_rejects_browser_commercial_or_identity_fields(billing, body):
    client, provider = billing
    assert checkout(client, **body).status_code == 422
    assert provider.create_calls == []


def test_portal_uses_only_authenticated_customer(billing):
    client, provider = billing
    pay(client, provider)
    assert client.post("/billing/portal", headers=HEADERS, json={}).status_code == 200
    bob = {**HEADERS, "Authorization": "Bearer bob"}
    assert client.post("/billing/portal", headers=bob, json={}).status_code == 409
    assert (
        client.post("/billing/portal", headers=bob, json={"customer_id": "cust_alice"}).status_code
        == 422
    )
    assert provider.portal_calls == ["cust_alice"]


def test_cancellation_preserves_paid_period(billing):
    client, provider = billing
    pay(client, provider)
    provider.subscription.update(status="canceled", updated_at=datetime.now(UTC).isoformat())
    assert event(client, "subscription.canceled", "evt_cancel").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingSubscription)).status == "canceled"
        assert session.scalar(select(PaidPeriod)).status == "active"


@pytest.mark.parametrize(
    "status,kind,expected",
    [
        ("refunded", "refund.created", "revoked"),
        ("chargedBack", "dispute.created", "frozen"),
        ("partialRefund", "refund.created", "active"),
    ],
)
def test_refund_and_dispute_project_verified_transaction_only(billing, status, kind, expected):
    client, provider = billing
    pay(client, provider)
    provider.transactions["tx_test"].update(
        status=status, refunded_amount=990 if status == "refunded" else 100
    )
    assert (
        event(
            client,
            kind,
            "evt_adjustment",
            {
                "id": "adjustment_test",
                "mode": "test",
                "subscription": "sub_test",
                "transaction": "tx_test",
            },
        ).status_code
        == 200
    )
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == expected
        inbox = session.scalar(
            select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == "evt_adjustment")
        )
        assert inbox.status == ("review" if status == "partialRefund" else "processed")
        assert session.scalar(select(BillingAccount)).blocked == (status == "chargedBack")
    if status == "chargedBack":
        response = checkout(client, key="after_dispute_123")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "BILLING_REVIEW_REQUIRED"


def test_provider_failure_persists_retry_without_half_grant(billing):
    client, provider = billing
    bind(client, provider)
    provider.fail_transaction = True
    assert event(client, "subscription.paid", "evt_failure").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        row = session.scalar(
            select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == "evt_failure")
        )
        assert row.status == "retry" and row.attempts == 1
        assert session.scalar(select(PaidPeriod)) is None
        assert (
            session.scalar(select(UsagePeriod).where(UsagePeriod.entitlement_type == "pro_paid"))
            is None
        )
    provider.fail_transaction = False
    due(client)
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == "active"


def test_refunding_old_transaction_leaves_renewal_active(billing):
    client, provider = billing
    pay(client, provider)
    renewal = deepcopy(provider.transactions["tx_test"])
    start = renewal["period_end"]
    end = start + 30 * 24 * 60 * 60 * 1000
    renewal.update(id="tx_renewal", period_start=start, period_end=end)
    provider.transactions["tx_renewal"] = renewal
    provider.subscription.update(
        last_transaction_id="tx_renewal",
        current_period_start_date=datetime.fromtimestamp(start / 1000, UTC).isoformat(),
        current_period_end_date=datetime.fromtimestamp(end / 1000, UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    assert (
        event(
            client,
            "subscription.paid",
            "evt_renewal",
            {
                "id": "sub_test",
                "mode": "test",
                "last_transaction_id": "tx_renewal",
            },
        ).status_code
        == 200
    )
    process(client, provider)
    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    assert (
        event(
            client,
            "refund.created",
            "evt_old_refund",
            {
                "id": "refund_old",
                "mode": "test",
                "subscription": "sub_test",
                "transaction": "tx_test",
            },
        ).status_code
        == 200
    )
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert {row.transaction_id: row.status for row in session.scalars(select(PaidPeriod))} == {
            "tx_test": "revoked",
            "tx_renewal": "active",
        }


@pytest.mark.parametrize("path", ["/billing/checkout", "/billing/portal"])
def test_billing_write_routes_require_auth_and_allowed_origin(billing, path):
    client, provider = billing
    key = {"Idempotency-Key": "guards_key_123"}
    assert (
        client.post(path, headers={**key, "Origin": HEADERS["Origin"]}, json={}).status_code == 401
    )
    for origin in (None, "https://evil.test"):
        headers = {**key, "Authorization": "Bearer alice"}
        if origin:
            headers["Origin"] = origin
        assert client.post(path, headers=headers, json={}).status_code == 403
    assert provider.create_calls == provider.portal_calls == []
