import hashlib
import hmac
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import BillingWebhookEvent, CheckoutSession, PaidPeriod
from app.services.billing_events import receive_event, reconcile_known
from app.services.creem_client import CreemCheckoutRejected, CreemError
from app.settings import Settings
from tests.test_auth_ownership import auth_settings
from tests.test_creem_billing import (
    HEADERS,
    SECRET,
    bind,
    checkout,
    event,
    process,
)
from tests.test_creem_billing import (
    billing as billing,
)


def test_product_lookup_failure_can_retry_without_duplicate_post(billing, monkeypatch):
    client, provider = billing
    original = provider.get_product
    monkeypatch.setattr(provider, "get_product", lambda _: (_ for _ in ()).throw(CreemError()))
    first = checkout(client)
    assert first.json()["status"] == "failed"
    assert provider.create_calls == []
    monkeypatch.setattr(provider, "get_product", original)
    assert checkout(client, key="recovery_key_12").json()["status"] == "pending"
    assert len(provider.create_calls) == 1


def test_explicit_invalid_checkout_input_is_failed_and_requires_a_new_key(billing, monkeypatch):
    client, provider = billing
    original = provider.create_checkout
    calls = []

    def rejected(**payload):
        calls.append(payload)
        raise CreemCheckoutRejected("Checkout request was rejected")

    monkeypatch.setattr(provider, "create_checkout", rejected)
    response = checkout(client)
    assert response.json()["status"] == "failed"
    assert response.json()["checkout_url"] is None
    assert checkout(client).json() == response.json()
    assert len(calls) == 1
    with client.app.state.session_factory() as session:
        row = session.scalar(select(CheckoutSession))
        assert row.error_code == "CHECKOUT_REQUEST_REJECTED" and row.provider_id is None
        assert session.scalar(select(PaidPeriod)) is None
    monkeypatch.setattr(provider, "create_checkout", original)
    assert checkout(client, key="fixed_config_new_key").json()["status"] == "pending"
    assert len(provider.create_calls) == 1


def test_create_response_can_omit_request_id_but_binding_uses_retrieved_correlation(
    billing, monkeypatch,
):
    client, provider = billing
    original = provider.create_checkout

    def without_optional_request_id(**payload):
        result = original(**payload)
        result.pop("request_id")
        return result

    monkeypatch.setattr(provider, "create_checkout", without_optional_request_id)
    response = checkout(client)
    assert response.json()["status"] == "pending"
    assert checkout(client).json() == response.json()
    assert len(provider.create_calls) == 1
    with client.app.state.session_factory() as session:
        row = session.scalar(select(CheckoutSession))
        assert row.provider_id == "ch_test" and row.status == "pending"
        assert session.scalar(select(PaidPeriod)) is None
    provider.checkout["status"] = "completed"
    assert event(client, "checkout.completed", "evt_optional_request_id",
                 {"id": "ch_test", "mode": "test"}).status_code == 200
    process(client, provider)
    assert event(client, "subscription.paid", "evt_optional_paid").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CheckoutSession)).status == "completed"
        assert session.scalar(select(PaidPeriod)).transaction_id == "tx_test"


@pytest.mark.parametrize("correlation", ["different_intent", "", None, {}, []])
def test_create_response_with_conflicting_correlation_stays_uncertain(
    billing, monkeypatch, correlation,
):
    client, provider = billing
    original = provider.create_checkout

    def conflicting(**payload):
        result = original(**payload)
        result["request_id"] = correlation
        return result

    monkeypatch.setattr(provider, "create_checkout", conflicting)
    assert checkout(client).json()["status"] == "uncertain"
    assert checkout(client, key="another_key_123").json()["status"] == "uncertain"
    assert len(provider.create_calls) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CheckoutSession)).provider_id is None
        assert session.scalar(select(PaidPeriod)) is None


def test_expired_subscription_still_blocks_until_provider_cancels(billing):
    # Official webhook contract explicitly says expired may still retry billing.
    client, provider = billing
    bind(client, provider)
    provider.subscription.update(status="expired", updated_at=datetime.now(UTC).isoformat())
    assert event(client, "subscription.expired", "evt_expired").status_code == 200
    process(client, provider)
    assert checkout(client, key="new_try_123").status_code == 409


def test_unknown_checkout_outcome_recovers_from_signed_binding(billing):
    client, provider = billing
    provider.timeout = True
    assert checkout(client).json()["status"] == "uncertain"
    provider.checkout["status"] = "completed"
    assert (
        event(
            client, "checkout.completed", "evt_recovery", {"id": "ch_test", "mode": "test"}
        ).status_code
        == 200
    )
    process(client, provider)
    assert event(client, "subscription.paid", "evt_paid_after_timeout").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(CheckoutSession)).status == "completed"
        assert session.scalar(select(PaidPeriod)).transaction_id == "tx_test"
    assert len(provider.create_calls) == 1


def test_inbox_rollback_and_conflicting_replay(billing):
    client, _ = billing
    raw = json.dumps(
        {
            "id": "evt_rollback",
            "eventType": "subscription.active",
            "object": {"id": "sub_test", "mode": "test"},
        }
    ).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    with client.app.state.session_factory() as session:
        receive_event(session, raw, signature, SECRET)
        session.rollback()
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None
    assert event(client, "subscription.active", "evt_same").status_code == 200
    assert event(client, "subscription.paid", "evt_same").status_code == 400


def test_bad_payment_evidence_never_grants(billing):
    client, provider = billing
    bind(client, provider)
    provider.transactions["tx_test"]["amount_paid"] = 1
    assert event(client, "subscription.paid", "evt_underpaid").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None


def test_oversize_and_unknown_event_handling(billing):
    client, provider = billing
    assert (
        client.post(
            "/webhooks/creem",
            content=b"x" * (256 * 1024 + 1),
            headers={"creem-signature": "0" * 64},
        ).status_code
        == 413
    )
    assert event(client, "subscription.future_event", "evt_unknown").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        row = session.scalar(select(BillingWebhookEvent))
        assert row.status == "review" and row.error_code == "UNHANDLED_EVENT"


def test_reconciliation_recovers_missing_paid_notification(billing):
    client, provider = billing
    bind(client, provider)
    report = reconcile_known(client.app.state.session_factory, provider)
    assert report["failed"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).transaction_id == "tx_test"
    state = client.get("/billing/me", headers=HEADERS).json()
    assert state["sync_state"] == "ready" and state["plan"] == "pro"


@pytest.mark.parametrize(
    "overrides",
    [
        {"billing_environment": "live"},
        {"environment": "production"},
        {"creem_api_key": ""},
        {"creem_webhook_secret": ""},
        {"creem_success_url": "https://evil.example/return"},
        {"creem_success_url": "http://localhost:3000/return?redirect=evil"},
    ],
)
def test_config_rejects_live_missing_secrets_and_foreign_return(tmp_path, overrides):
    fields = auth_settings(tmp_path).model_dump()
    fields.update(
        usage_enabled=True,
        paid_usage_enabled=True,
        creem_enabled=True,
        creem_api_key="offline_key",
        creem_webhook_secret=SECRET,
        creem_product_id="prod_test",
        creem_success_url="http://localhost:3000/account",
    )
    fields.update(overrides)
    with pytest.raises(ValueError):
        Settings(_env_file=None, **fields)
