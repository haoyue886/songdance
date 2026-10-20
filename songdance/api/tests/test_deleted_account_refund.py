"""Retained payment records accept verified refunds after local account erasure."""

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import (
    AccountDeletion,
    AuthIdentity,
    BillingCancellation,
    BillingWebhookEvent,
    PaidPeriod,
    UsagePeriod,
    User,
)
from app.services.billing_cancellations import process_cancellations
from tests.test_account_deletion import deletion_client as deletion_client
from tests.test_account_deletion import process, request_deletion
from tests.test_creem_billing import HEADERS, event, pay
from tests.test_creem_billing import billing as billing
from tests.test_creem_billing import process as process_billing


@pytest.mark.parametrize("completed", [False, True])
@pytest.mark.parametrize("status,kind,expected", [
    ("refunded", "refund.created", "revoked"),
    ("partialRefund", "refund.created", "active"),
    ("chargedBack", "dispute.created", "frozen"),
])
def test_financial_event_after_deletion_updates_only_retained_grant(
    deletion_client, completed, status, kind, expected
):
    client, provider = deletion_client
    pay(client, provider)
    target = client.get("/me", headers=HEADERS).json()["id"]
    factory = client.app.state.session_factory
    with factory() as session:
        old = session.scalars(select(PaidPeriod)).one()
        grant_id, period_id = old.id, old.usage_period_id
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == 1
    if completed:
        assert process(client, provider) == 1
    with factory() as session:
        assert not session.get(User, target).active
        expected_deletion = "completed" if completed else "pending"
        assert session.scalars(select(AccountDeletion)).one().status == expected_deletion
    provider.transactions["tx_test"].update(status=status, refunded_amount=990)
    assert event(client, kind, "evt_after_delete", {
        "id": "financial_event", "mode": "test",
        "subscription": "sub_test", "transaction": "tx_test",
    }).status_code == 200
    assert process_billing(client, provider) == 1
    with factory() as session:
        paid = session.scalars(select(PaidPeriod)).one()
        assert paid.id == grant_id and paid.usage_period_id == period_id and paid.status == expected
        inbox = session.scalars(select(BillingWebhookEvent).where(
            BillingWebhookEvent.event_id == "evt_after_delete"
        )).one()
        assert inbox.status == ("review" if status == "partialRefund" else "processed")
        assert inbox.error_code == ("PARTIAL_REFUND_REVIEW" if status == "partialRefund" else None)
        assert session.scalars(select(AccountDeletion)).one().status == expected_deletion
    assert process_cancellations(factory, provider) == (1 if status == "refunded" else 0)
    if status == "refunded":
        with factory() as session:
            cancellation = session.scalars(select(BillingCancellation)).one()
            assert cancellation.status == "verified" and cancellation.attempts == 1
    assert process_billing(client, provider) == process_cancellations(factory, provider) == 0
    with factory() as session:
        assert not session.get(User, target).active
        assert (session.get(User, target).email is None) is completed
        assert len(session.scalars(select(User)).all()) == 1
        assert len(session.scalars(select(AuthIdentity)).all()) == 1
        usage = session.scalars(select(UsagePeriod)).one()
        assert usage.id == period_id
        assert (usage.limit_units, usage.consumed_units, usage.reserved_units) == (
            1800, 0, 0,
        )
        has_cancel = session.scalar(select(BillingCancellation.id)) is not None
        assert has_cancel is (status == "refunded")
    assert provider.cancel_calls == ["sub_test"]


def test_new_payment_after_completed_deletion_cannot_create_a_new_period(deletion_client):
    client, provider = deletion_client
    pay(client, provider)
    assert request_deletion(client).status_code == 202
    assert process(client, provider) == process(client, provider) == 1
    transaction = deepcopy(provider.transactions["tx_test"])
    start = transaction["period_end"]
    end = start + 30 * 86400000
    transaction.update(id="tx_after_deletion", period_start=start, period_end=end)
    provider.transactions[transaction["id"]] = transaction
    # Keep the subscription stopped so this isolates new grant rejection from
    # the separate reactivation-obligation checkpoint.
    provider.subscription.update(
        last_transaction_id=transaction["id"],
        current_period_start_date=datetime.fromtimestamp(start / 1000, UTC).isoformat(),
        current_period_end_date=datetime.fromtimestamp(end / 1000, UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    assert event(client, "subscription.paid", "evt_new_after_deletion", {
        "id": "sub_test", "mode": "test", "last_transaction_id": transaction["id"],
    }).status_code == 200
    assert process_billing(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalars(select(PaidPeriod.transaction_id)).all() == ["tx_test"]
        assert len(session.scalars(select(UsagePeriod)).all()) == 1
        row = session.scalars(select(BillingWebhookEvent).where(
            BillingWebhookEvent.event_id == "evt_new_after_deletion"
        )).one()
        assert row.status == "retry" and row.error_code == "PROVIDER_OR_BINDING_REVIEW"
        assert session.scalars(select(AccountDeletion)).one().status == "completed"
