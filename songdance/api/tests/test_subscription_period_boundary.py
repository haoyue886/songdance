"""Local provider facts and a fixed clock; no real renewal or supplier payment."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import BillingSubscription, BillingWebhookEvent, PaidPeriod, UsagePeriod
from app.services.billing_events import sync_transaction
from tests.test_billing_recovery import renewal
from tests.test_creem_billing import HEADERS, event, pay, process
from tests.test_creem_billing import billing as billing
from tests.test_cross_period_jobs import period_clock as period_clock


def first_period(client, provider, clock):
    start = clock(2030, 1, 1, tzinfo=clock.current.tzinfo)
    end = clock(2030, 2, 1, tzinfo=clock.current.tzinfo)
    provider.transactions["tx_test"].update(
        period_start=int(start.timestamp() * 1000), period_end=int(end.timestamp() * 1000)
    )
    provider.subscription.update(
        current_period_start_date=start.isoformat(),
        current_period_end_date=end.isoformat(),
        updated_at=clock.current.isoformat(),
    )
    pay(client, provider)
    return end


@pytest.mark.parametrize("status", ["canceled", "scheduled_cancel", "past_due", "unpaid"])
def test_subscription_status_does_not_extend_or_shorten_verified_paid_period(
    billing, period_clock, status
):
    client, provider = billing
    boundary = first_period(client, provider, period_clock)
    provider.subscription.update(status=status, updated_at=period_clock.current.isoformat())
    assert event(client, f"subscription.{status}", "evt_state").status_code == 200
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalars(select(BillingSubscription)).one().status == status
        inbox = session.scalars(select(BillingWebhookEvent).where(
            BillingWebhookEvent.event_id == "evt_state"
        )).one()
        assert inbox.status == "processed" and inbox.error_code is None
    summary = client.get("/billing/me", headers=HEADERS).json()
    assert (summary["plan"], summary["remaining"]) == ("pro", 1800)

    period_clock.current = boundary
    summary = client.get("/billing/me", headers=HEADERS).json()
    assert (summary["plan"], summary["remaining"]) == ("free", 1)
    with client.app.state.session_factory() as session:
        paid = session.scalars(select(PaidPeriod)).one()
        usage = session.get(UsagePeriod, paid.usage_period_id)
        assert paid.status == "active" and paid.period_end == boundary.replace(tzinfo=None)
        assert (usage.limit_units, usage.consumed_units, usage.reserved_units) == (1800, 0, 0)
    assert provider.cancel_calls == [] and len(provider.create_calls) == 1


@pytest.mark.parametrize("failed_status", ["declined", "uncollectible"])
def test_failed_renewal_then_verified_recovery_grants_one_new_period(
    billing, period_clock, failed_status
):
    client, provider = billing
    boundary = first_period(client, provider, period_clock)
    tx = renewal(provider)
    provider.transactions[tx["id"]].update(status=failed_status, amount_paid=0)
    period_clock.current = boundary
    # A paid-shaped notification cannot substitute for failed invoice facts.
    obj = {"id": "sub_test", "mode": "test", "last_transaction_id": tx["id"]}
    assert event(client, "subscription.paid", "evt_failed_renewal", obj).status_code == 200
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(PaidPeriod)).all()) == 1
        inbox = session.scalars(select(BillingWebhookEvent).where(
            BillingWebhookEvent.event_id == "evt_failed_renewal"
        )).one()
        assert inbox.status == "retry"
    assert client.get("/billing/me", headers=HEADERS).json()["plan"] == "free"

    provider.transactions[tx["id"]].update(status="paid", amount_paid=990)
    provider.subscription.update(status="active", updated_at=period_clock.current.isoformat())
    for _ in range(3):
        assert event(client, "subscription.paid", "evt_recovered_renewal", obj).status_code == 200
        process(client, provider)
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod).order_by(PaidPeriod.period_start)).all()
        assert len(periods) == 2 and periods[0].period_end == periods[1].period_start
        baseline = [(p.id, p.usage_period_id, p.status) for p in periods]
    # The original failed event becomes due later and must not grant again.
    period_clock.current += timedelta(minutes=2)
    assert process(client, provider) == 1
    with client.app.state.session_factory.begin() as session:
        assert not sync_transaction(session, provider, "sub_test", tx["id"])
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod).order_by(PaidPeriod.period_start)).all()
        assert [(p.id, p.usage_period_id, p.status) for p in periods] == baseline
        assert all(session.get(UsagePeriod, p.usage_period_id).limit_units == 1800 for p in periods)
        for event_id in ("evt_failed_renewal", "evt_recovered_renewal"):
            inbox = session.scalars(select(BillingWebhookEvent).where(
                BillingWebhookEvent.event_id == event_id
            )).one()
            assert inbox.status == "processed" and inbox.error_code is None
    summary = client.get("/billing/me", headers=HEADERS).json()
    assert (summary["plan"], summary["remaining"]) == ("pro", 1800)
    assert provider.cancel_calls == [] and len(provider.create_calls) == 1
