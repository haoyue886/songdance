"""Unpaid hosted checkouts stay recoverable without granting or creating twice."""

import pytest
from sqlalchemy import select

from app.models import BillingSubscription, CheckoutSession, PaidPeriod, UsagePeriod
from app.services.billing_events import sync_checkout, sync_transaction
from tests.test_creem_billing import HEADERS, checkout, event, process
from tests.test_creem_billing import billing as billing


@pytest.mark.parametrize("remote_status", ["pending", "processing"])
def test_unpaid_checkout_reuses_original_link_then_grants_once(billing, remote_status):
    client, provider = billing
    original = checkout(client).json()
    provider.checkout["status"] = remote_status
    # Closing the browser or a card rejection is not evidence of expiration.
    with client.app.state.session_factory.begin() as session:
        assert sync_checkout(session, provider, "ch_test") is None
    summary = client.get("/billing/me", headers=HEADERS).json()
    assert summary["plan"] == "free" and summary["sync_state"] == "payment_confirming"
    assert checkout(client, key="different_browser_key").json() == original
    assert len(provider.create_calls) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None
        assert session.scalar(select(BillingSubscription)) is None

    provider.checkout["status"] = "completed"
    assert event(client, "checkout.completed", "evt_recovered_checkout",
                 {"id": "ch_test", "mode": "test"}).status_code == 200
    process(client, provider)
    for _ in range(3):
        assert event(client, "subscription.paid", "evt_recovered_paid").status_code == 200
        process(client, provider)
    assert event(client, "subscription.active", "evt_recovered_active").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        paid = session.scalars(select(PaidPeriod)).one()
        usage = session.get(UsagePeriod, paid.usage_period_id)
        assert paid.status == "active"
        assert (usage.limit_units, usage.consumed_units, usage.reserved_units) == (1800, 0, 0)
        assert session.scalars(select(CheckoutSession)).one().id == original["id"]
    assert len(provider.create_calls) == 1
    assert client.get("/billing/me", headers=HEADERS).json()["sync_state"] == "ready"


def test_only_provider_confirmed_expiration_allows_a_new_checkout(billing):
    client, provider = billing
    first = checkout(client).json()
    assert checkout(client, key="premature_replacement").json()["id"] == first["id"]
    provider.checkout["status"] = "expired"
    with client.app.state.session_factory.begin() as session:
        assert sync_checkout(session, provider, "ch_test") is None
    assert checkout(client).json()["status"] == "expired"
    assert len(provider.create_calls) == 1
    original_create = provider.create_checkout

    def distinct_checkout(**payload):
        result = original_create(**payload)
        provider.checkout["id"] = result["id"] = "ch_replacement"
        result["checkout_url"] = "https://www.creem.io/test/checkout/ch_replacement"
        return result

    provider.create_checkout = distinct_checkout
    second = checkout(client, key="confirmed_expiration_retry").json()
    assert second["status"] == "pending" and second["id"] != first["id"]
    with client.app.state.session_factory() as session:
        assert session.get(CheckoutSession, first["id"]).status == "expired"
        assert session.scalar(select(PaidPeriod)) is None
        assert len(session.scalars(select(CheckoutSession)).all()) == 2
    assert len(provider.create_calls) == 2


@pytest.mark.parametrize("transaction_status", ["pending", "failed", "voided"])
def test_unpaid_invoice_never_grants_even_with_a_completed_checkout(billing, transaction_status):
    client, provider = billing
    checkout(client)
    provider.checkout["status"] = "completed"
    provider.transactions["tx_test"].update(status=transaction_status, amount_paid=0)
    with client.app.state.session_factory.begin() as session:
        sync_checkout(session, provider, "ch_test")
    with pytest.raises(ValueError, match="transaction_not_paid"):
        with client.app.state.session_factory.begin() as session:
            sync_transaction(session, provider, "sub_test", "tx_test")
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None
    assert client.get("/billing/me", headers=HEADERS).json()["plan"] == "free"
