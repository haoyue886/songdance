"""Repurchase gates and old-refund isolation using offline provider objects."""

from copy import deepcopy
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import BillingCancellation, BillingSubscription, PaidPeriod, UsagePeriod
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import sync_checkout, sync_transaction
from tests.test_creem_billing import HEADERS, checkout, event, process
from tests.test_creem_billing import billing as billing
from tests.test_cross_period_jobs import period_clock as period_clock
from tests.test_subscription_period_boundary import first_period


def snapshot(row):
    return {column.key: getattr(row, column.key) for column in row.__mapper__.column_attrs}


@pytest.mark.parametrize("status", ["active", "scheduled_cancel", "expired", "past_due", "unpaid"])
def test_unstopped_subscription_blocks_new_checkout_even_after_paid_expiry(
    billing, period_clock, status
):
    client, provider = billing
    boundary = first_period(client, provider, period_clock)
    provider.subscription.update(status=status, updated_at=period_clock.current.isoformat())
    assert event(client, f"subscription.{status}", "evt_old_state").status_code == 200
    process(client, provider)
    with client.app.state.session_factory() as session:
        assert session.scalars(select(BillingSubscription)).one().status == status
    period_clock.current = boundary
    response = checkout(client, key="new_subscription_attempt")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SUBSCRIPTION_EXISTS"
    assert len(provider.create_calls) == 1


def test_expired_canceled_repurchase_preserves_history_and_old_refund_spares_new_period(
    billing, period_clock, monkeypatch
):
    client, provider = billing
    boundary = first_period(client, provider, period_clock)
    provider.subscription.update(status="canceled", updated_at=period_clock.current.isoformat())
    assert event(client, "subscription.canceled", "evt_old_canceled").status_code == 200
    process(client, provider)
    assert checkout(client, key="too_early_repurchase").status_code == 409
    assert len(provider.create_calls) == 1
    old_sub = deepcopy(provider.subscription)
    old_tx = deepcopy(provider.transactions["tx_test"])
    with client.app.state.session_factory() as session:
        old_paid = session.scalars(select(PaidPeriod)).one()
        old_grant = snapshot(old_paid)
        old_usage = snapshot(session.get(UsagePeriod, old_paid.usage_period_id))

    period_clock.current = boundary
    original_create = provider.create_checkout

    def new_checkout(**payload):
        reply = original_create(**payload)
        provider.checkout.update(id="ch_repurchase", subscription="sub_repurchase")
        reply.update(id="ch_repurchase", subscription="sub_repurchase",
                     checkout_url="https://www.creem.io/test/checkout/ch_repurchase")
        return reply

    monkeypatch.setattr(provider, "create_checkout", new_checkout)
    created = checkout(client, key="after_expiry_repurchase")
    assert created.status_code == 200 and created.json()["status"] == "pending"
    assert provider.create_calls[-1]["customer_id"] == "cust_alice"
    assert checkout(client, key="another_browser_key").json() == created.json()
    assert len(provider.create_calls) == 2

    end = boundary + timedelta(days=28)
    provider.subscription.update(
        id="sub_repurchase", status="active", last_transaction_id="tx_repurchase",
        current_period_start_date=boundary.isoformat(), current_period_end_date=end.isoformat(),
        updated_at=period_clock.current.isoformat(),
    )
    tx = {**old_tx, "id": "tx_repurchase", "subscription": "sub_repurchase",
          "period_start": int(boundary.timestamp() * 1000),
          "period_end": int(end.timestamp() * 1000)}
    provider.transactions[tx["id"]] = tx
    provider.checkout["status"] = "completed"
    monkeypatch.setattr(provider, "get_checkout", lambda ref: (
        deepcopy(provider.checkout) if ref == "ch_repurchase" else pytest.fail("wrong checkout")
    ))
    monkeypatch.setattr(provider, "get_subscription", lambda ref: deepcopy(
        old_sub if ref == "sub_test" else provider.subscription
        if ref == "sub_repurchase" else pytest.fail("wrong subscription")
    ))
    for _ in range(2):
        with client.app.state.session_factory.begin() as session:
            sync_checkout(session, provider, "ch_repurchase")
            sync_transaction(session, provider, "sub_repurchase", "tx_repurchase")
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod).order_by(PaidPeriod.period_start)).all()
        assert len(periods) == 2 and snapshot(periods[0]) == old_grant
        assert snapshot(session.get(UsagePeriod, periods[0].usage_period_id)) == old_usage
        new_grant = snapshot(periods[1])
        new_usage = snapshot(session.get(UsagePeriod, periods[1].usage_period_id))

    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    with client.app.state.session_factory.begin() as session:
        sync_transaction(session, provider, "sub_test", "tx_test", event_kind="refund.created")
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    assert process_cancellations(client.app.state.session_factory, provider) == 0
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod).order_by(PaidPeriod.period_start)).all()
        assert periods[0].status == "revoked" and snapshot(periods[1]) == new_grant
        assert snapshot(session.get(UsagePeriod, periods[0].usage_period_id)) == old_usage
        assert snapshot(session.get(UsagePeriod, periods[1].usage_period_id)) == new_usage
        cancellation = session.scalars(select(BillingCancellation)).one()
        assert cancellation.subscription_id == "sub_test" and cancellation.status == "verified"
    summary = client.get("/billing/me", headers=HEADERS).json()
    assert (summary["plan"], summary["remaining"]) == ("pro", 1800)
    assert provider.cancel_calls == [] and len(provider.create_calls) == 2
