"""Offline history recovery and durable full-refund cancellation regressions."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    BillingAccount,
    BillingCancellation,
    BillingSubscription,
    BillingWebhookEvent,
    PaidPeriod,
    UsagePeriod,
)
from app.services.billing import BillingMismatch
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import reconcile_known
from app.services.billing_reconciliation import scan_transactions
from app.services.creem_client import CreemError
from app.services.usage import _as_utc
from tests.test_creem_billing import (
    HEADERS,
    bind,
    checkout,
    due,
    event,
    pay,
    process,
)
from tests.test_creem_billing import (
    billing as billing,
)


def history(provider, count):
    latest = deepcopy(provider.transactions["tx_test"])
    duration = latest["period_end"] - latest["period_start"]
    provider.transactions = {}
    for index in range(count - 1):
        tx = deepcopy(latest)
        tx_id = f"tx_history_{index:03}"
        offset = (count - 1 - index) * duration
        tx.update(
            id=tx_id,
            period_start=latest["period_start"] - offset,
            period_end=latest["period_end"] - offset,
        )
        provider.transactions[tx_id] = tx
    provider.transactions["tx_test"] = latest


def page(items, *, total=None, number=1):
    total = len(items) if total is None else total
    pages = (total + 99) // 100
    return {
        "items": deepcopy(items),
        "pagination": {
            "total_records": total,
            "total_pages": pages,
            "current_page": number,
            "next_page": number + 1 if number < pages else None,
            "prev_page": number - 1 if number > 1 else None,
        },
    }


def refund(client, provider, event_id="evt_full_refund"):
    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    assert (
        event(
            client,
            "refund.created",
            event_id,
            {
                "id": "refund_test",
                "mode": "test",
                "subscription": "sub_test",
                "transaction": "tx_test",
            },
        ).status_code
        == 200
    )
    return process(client, provider)


def cancellation(client):
    with client.app.state.session_factory() as session:
        return session.scalars(select(BillingCancellation)).one()


def renewal(provider):
    tx = deepcopy(provider.transactions["tx_test"])
    start = tx["period_end"]
    end = start + tx["period_end"] - tx["period_start"]
    tx.update(id="tx_renewal", status="paid", period_start=start, period_end=end)
    tx.pop("refunded_amount", None)
    provider.transactions[tx["id"]] = tx
    provider.subscription.update(
        last_transaction_id=tx["id"],
        current_period_start_date=datetime.fromtimestamp(start / 1000, UTC).isoformat(),
        current_period_end_date=datetime.fromtimestamp(end / 1000, UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
    )
    return tx


def test_history_recovers_multiple_missed_cycles_through_the_durable_inbox(billing):
    client, provider = billing
    history(provider, 4)
    bind(client, provider)
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report == {
        "pages": 1,
        "scanned": 4,
        "queued": 4,
        "unbound": 0,
        "scan_failed": 0,
        "scan_complete": True,
    }
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None
        rows = session.scalars(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.event_type == "reconciliation.transaction"
            )
        ).all()
        assert len(rows) == 4
        assert all((row.status, row.attempts) == ("pending", 0) for row in rows)
    assert process(client, provider) == 4
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod)).all()
        assert {row.transaction_id for row in periods} == set(provider.transactions)
        assert all(row.status == "active" for row in periods)
        assert len({row.usage_period_id for row in periods}) == 4
        usage = session.get(UsagePeriod, periods[0].usage_period_id)
        usage.reserved_units, usage.consumed_units = 15, 30
        preserved = usage.id
        session.commit()
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 0
    assert process(client, provider) == 0
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(PaidPeriod)).all()) == 4
        usage = session.get(UsagePeriod, preserved)
        assert (usage.limit_units, usage.reserved_units, usage.consumed_units) == (1800, 15, 30)


def test_reconcile_known_recovers_checkout_and_latest_then_queues_older_history(billing):
    client, provider = billing
    history(provider, 4)
    assert checkout(client).status_code == 200
    provider.checkout["status"] = "completed"
    report = reconcile_known(client.app.state.session_factory, provider)
    assert (report["completed"], report["failed"], report["queued"]) == (2, 0, 4)
    assert report["scan_complete"] is True
    with client.app.state.session_factory() as session:
        assert session.scalars(select(PaidPeriod.transaction_id)).all() == ["tx_test"]
        assert session.scalar(select(BillingSubscription)).provider_id == "sub_test"
    assert process(client, provider) == 4
    assert reconcile_known(client.app.state.session_factory, provider)["queued"] == 0
    with client.app.state.session_factory() as session:
        assert set(session.scalars(select(PaidPeriod.transaction_id))) == set(provider.transactions)


def test_history_scan_paginates_all_transactions_at_one_hundred_per_page(billing):
    client, provider = billing
    history(provider, 102)
    bind(client, provider)
    report = scan_transactions(client.app.state.session_factory, provider)
    assert provider.list_calls == [(1, 100), (2, 100)]
    assert (report["pages"], report["scanned"], report["queued"]) == (2, 102, 102)
    assert report["scan_complete"] is True and report["scan_failed"] == 0
    assert process(client, provider) == 100
    assert process(client, provider) == 2
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(PaidPeriod)).all()) == 102


def test_unbound_history_is_reviewed_without_claiming_same_email_identity(billing):
    client, provider = billing
    alice = client.get("/me", headers=HEADERS).json()
    bob = client.get("/me", headers={**HEADERS, "Authorization": "Bearer bob"}).json()
    assert alice["email"] == bob["email"] and alice["id"] != bob["id"]
    provider.transactions["tx_test"].update(
        email=alice["email"],
        address="private-address",
        description="private-description",
        metadata={"user_id": alice["id"], "email": alice["email"]},
    )
    report = scan_transactions(client.app.state.session_factory, provider)
    assert (report["queued"], report["unbound"]) == (1, 1)
    assert process(client, provider) == 0
    with client.app.state.session_factory() as session:
        row = session.scalars(select(BillingWebhookEvent)).one()
        assert (row.status, row.error_code) == ("review", "RECONCILIATION_UNBOUND")
        assert alice["email"] not in row.references and alice["id"] not in row.references
        assert "private-" not in row.references
        assert session.scalar(select(BillingSubscription)) is None
        assert session.scalar(select(BillingAccount)) is None
        assert session.scalar(select(PaidPeriod)) is None
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 0
    bind(client, provider)
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 0
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).user_id == alice["id"]


@pytest.mark.parametrize(
    "status,expected,error",
    [
        ("refunded", "revoked", None),
        ("partialRefund", "active", "PARTIAL_REFUND_REVIEW"),
        ("chargedBack", "frozen", None),
    ],
)
def test_recovered_history_uses_current_authoritative_financial_facts(
    billing, status, expected, error
):
    client, provider = billing
    bind(client, provider)
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 1
    provider.transactions["tx_test"].update(status=status, refunded_amount=990)
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == expected
        row = session.scalars(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.event_type == "reconciliation.transaction"
            )
        ).one()
        assert row.error_code == error
        assert row.status == ("review" if error else "processed")
        intent = session.scalar(select(BillingCancellation))
        assert (intent is not None) == (status == "refunded")


def test_changed_financial_state_queues_once_without_resetting_prior_inbox(billing):
    client, provider = billing
    pay(client, provider)
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 1
    assert process(client, provider) == 1
    provider.transactions["tx_test"].update(status="partialRefund", refunded_amount=100)
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 1
    assert process(client, provider) == 1
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 0
    with client.app.state.session_factory() as session:
        rows = session.scalars(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.event_type == "reconciliation.transaction"
            )
        ).all()
        assert {(row.status, row.attempts) for row in rows} == {("processed", 1), ("review", 1)}
        assert session.scalar(select(PaidPeriod)).status == "active"
        assert session.scalar(select(BillingCancellation)) is None


@pytest.mark.parametrize("status", ["pending", "uncollectible", "declined", "canceled", "void"])
def test_nonfinancial_invoices_do_not_create_entitlements(billing, status):
    client, provider = billing
    provider.transactions["tx_test"]["status"] = status
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_complete"] is True and report["scanned"] == 1
    assert report["queued"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None
        assert session.scalar(select(PaidPeriod)) is None


def test_payment_entries_are_not_mistaken_for_subscription_invoice_grants(billing):
    client, provider = billing
    provider.transactions["tx_test"]["type"] = "payment"
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_complete"] is True and report["queued"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_records", -1),
        ("total_records", True),
        ("total_records", "1"),
        ("total_records", 101),
        ("total_pages", 2),
        ("total_pages", True),
        ("current_page", 2),
        ("current_page", True),
        ("next_page", 2),
        ("prev_page", 0),
    ],
)
def test_invalid_pagination_never_reports_complete_or_queues_a_page(
    billing, monkeypatch, field, value
):
    client, provider = billing
    response = page(list(provider.transactions.values()))
    response["pagination"][field] = value
    monkeypatch.setattr(provider, "list_transactions", lambda **kwargs: deepcopy(response))
    report = scan_transactions(client.app.state.session_factory, provider)
    assert (report["scan_failed"], report["pages"], report["queued"]) == (1, 0, 0)
    assert report["scan_complete"] is False
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None


@pytest.mark.parametrize("mode", [None, "prod", "live"])
def test_one_invalid_mode_rejects_the_entire_listing_page(billing, monkeypatch, mode):
    client, provider = billing
    history(provider, 2)
    response = page(list(provider.transactions.values()))
    response["items"][1]["mode"] = mode
    monkeypatch.setattr(provider, "list_transactions", lambda **kwargs: deepcopy(response))
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert report["queued"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None


def test_duplicate_id_inside_one_page_is_rejected_before_queueing(billing, monkeypatch):
    client, provider = billing
    tx = provider.transactions["tx_test"]
    monkeypatch.setattr(provider, "list_transactions", lambda **kwargs: page([tx, tx]))
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert report["queued"] == 0


@pytest.mark.parametrize("change", ["repeated_id", "changed_total", "provider_failure"])
def test_partial_history_scan_never_falsely_reports_complete(billing, monkeypatch, change):
    client, provider = billing
    history(provider, 101)
    bind(client, provider)
    original = provider.list_transactions

    def listing(**kwargs):
        response = original(**kwargs)
        if kwargs["page_number"] == 2:
            if change == "provider_failure":
                raise CreemError("offline listing unavailable")
            if change == "repeated_id":
                response["items"][0]["id"] = next(iter(provider.transactions))
            else:
                response["pagination"]["total_records"] = 102
                response["items"].append(deepcopy(response["items"][0]))
        return response

    monkeypatch.setattr(provider, "list_transactions", listing)
    report = scan_transactions(client.app.state.session_factory, provider)
    assert (report["pages"], report["scanned"], report["queued"]) == (1, 100, 100)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert provider.list_calls == [(1, 100), (2, 100)]


def test_page_budget_leaves_scan_incomplete_and_rescan_recovers_remaining_items(billing):
    client, provider = billing
    history(provider, 101)
    bind(client, provider)
    report = scan_transactions(client.app.state.session_factory, provider, max_pages=1)
    assert report["scan_complete"] is False and report["pages"] == 1
    assert report["queued"] == 100 and provider.list_calls == [(1, 100)]
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_complete"] is True and report["queued"] == 1


@pytest.mark.parametrize("max_pages", [0, 1001, True, "100", 1.0])
def test_invalid_page_budget_is_rejected_before_provider_calls(billing, max_pages):
    client, provider = billing
    with pytest.raises(ValueError):
        scan_transactions(client.app.state.session_factory, provider, max_pages=max_pages)
    assert provider.list_calls == []


def test_provider_listing_failure_is_explicit_and_creates_no_grant(billing, monkeypatch):
    client, provider = billing

    def failed_listing(**kwargs):
        raise CreemError("offline provider unavailable")

    monkeypatch.setattr(provider, "list_transactions", failed_listing)
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert report["queued"] == 0
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)) is None


@pytest.mark.parametrize(
    "field,number,value", [("prev_page", 2, True), ("prev_page", 2, 1.0), ("next_page", 1, 2.0)]
)
def test_pagination_navigation_requires_integer_page_numbers(
    billing, monkeypatch, field, number, value
):
    client, provider = billing
    history(provider, 101)
    bind(client, provider)
    original = provider.list_transactions

    def listing(**kwargs):
        response = original(**kwargs)
        if kwargs["page_number"] == number:
            response["pagination"][field] = value
        return response

    monkeypatch.setattr(provider, "list_transactions", listing)
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert report["pages"] == number - 1 and report["queued"] == (number - 1) * 100


@pytest.mark.parametrize(
    "field", ["total_records", "total_pages", "current_page", "next_page", "prev_page"]
)
def test_pagination_requires_all_contract_fields_even_null_navigation(billing, monkeypatch, field):
    client, provider = billing
    response = page(list(provider.transactions.values()))
    del response["pagination"][field]
    monkeypatch.setattr(provider, "list_transactions", lambda **kwargs: deepcopy(response))
    report = scan_transactions(client.app.state.session_factory, provider)
    assert report["scan_failed"] == 1 and report["scan_complete"] is False
    assert report["pages"] == 0 and report["queued"] == 0


def test_signed_external_event_cannot_forge_reconciliation_inbox_record(billing):
    client, _ = billing
    assert (
        event(
            client,
            "reconciliation.transaction",
            "evt_forged",
            {"id": "tx_test", "mode": "test", "subscription": "sub_test", "transaction": "tx_test"},
        ).status_code
        == 400
    )
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingWebhookEvent)) is None


def test_full_refund_revocation_and_cancellation_intent_commit_atomically(billing):
    client, provider = billing
    pay(client, provider)
    assert refund(client, provider) == 1
    with client.app.state.session_factory() as session:
        paid = session.scalars(select(PaidPeriod)).one()
        intent = session.scalars(select(BillingCancellation)).one()
        assert paid.status == "revoked"
        assert (intent.paid_period_id, intent.user_id, intent.transaction_id) == (
            paid.id,
            paid.user_id,
            paid.transaction_id,
        )
        assert (intent.subscription_id, intent.environment) == ("sub_test", "test")
        assert (intent.status, intent.attempts, intent.error_code) == ("pending", 0, None)
    assert provider.cancel_calls == []


def test_failed_intent_persistence_rolls_back_refund_projection_then_recovers(billing, monkeypatch):
    from app.services import billing_cancellations

    client, provider = billing
    pay(client, provider)
    original = billing_cancellations.request_refund_cancellation

    def failed_intent(session, paid):
        original(session, paid)
        session.flush()
        raise BillingMismatch("simulated_cancellation_persistence_failure")

    monkeypatch.setattr(billing_cancellations, "request_refund_cancellation", failed_intent)
    assert refund(client, provider) == 1
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == "active"
        assert session.scalar(select(BillingCancellation)) is None
        row = session.scalars(
            select(BillingWebhookEvent).where(BillingWebhookEvent.event_id == "evt_full_refund")
        ).one()
        assert (row.status, row.attempts) == ("retry", 1)
    monkeypatch.setattr(billing_cancellations, "request_refund_cancellation", original)
    due(client)
    assert process(client, provider) == 1
    assert cancellation(client).status == "pending"
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == "revoked"


def test_cancel_is_verified_by_get_not_only_by_successful_post_response(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    original = provider.cancel_subscription

    def ineffective_post(subscription_id):
        provider.cancel_calls.append(subscription_id)
        return {**provider.subscription, "status": "canceled"}

    monkeypatch.setattr(provider, "cancel_subscription", ineffective_post)
    current = datetime.now(UTC) + timedelta(minutes=1)
    assert process_cancellations(client.app.state.session_factory, provider, now=current) == 1
    row = cancellation(client)
    assert (row.status, row.attempts, row.error_code) == (
        "retry",
        1,
        "CANCELLATION_CONFIRMATION_REQUIRED",
    )
    assert _as_utc(row.next_attempt_at) == current + timedelta(seconds=60)
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=current + timedelta(seconds=59)
        )
        == 0
    )
    monkeypatch.setattr(provider, "cancel_subscription", original)
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=_as_utc(row.next_attempt_at)
        )
        == 1
    )
    assert cancellation(client).status == "verified"
    assert provider.cancel_calls == ["sub_test", "sub_test"]


def test_lost_successful_cancel_response_recovers_by_get_without_second_post(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    original = provider.cancel_subscription

    def lost_response(subscription_id):
        original(subscription_id)
        raise CreemError("unknown cancellation outcome")

    monkeypatch.setattr(provider, "cancel_subscription", lost_response)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert row.status == "retry" and provider.subscription["status"] == "canceled"
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=_as_utc(row.next_attempt_at)
        )
        == 1
    )
    row = cancellation(client)
    assert (row.status, row.attempts, row.error_code) == ("verified", 2, None)
    assert provider.cancel_calls == ["sub_test"]
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=datetime.now(UTC) + timedelta(days=1)
        )
        == 0
    )


@pytest.mark.parametrize("status", ["canceled", "scheduled_cancel"])
def test_already_stopped_subscription_is_verified_without_post(billing, status):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    provider.subscription.update(status=status, updated_at=datetime.now(UTC).isoformat())
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    assert cancellation(client).status == "verified" and provider.cancel_calls == []


def test_stale_subscription_snapshot_enters_permanent_review_without_post(billing):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    old_snapshot = deepcopy(provider.subscription)
    provider.subscription["updated_at"] = datetime.now(UTC).isoformat()
    assert event(client, "subscription.update", "evt_latest_state").status_code == 200
    assert process(client, provider) == 1
    provider.subscription.update(old_snapshot)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert (row.status, row.error_code) == ("review", "STALE_SUBSCRIPTION_REVIEW")
    assert provider.cancel_calls == []
    provider.subscription["updated_at"] = datetime.now(UTC).isoformat()
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=datetime.now(UTC) + timedelta(days=1)
        )
        == 0
    )
    assert refund(client, provider, "evt_duplicate_after_stale") == 1
    assert cancellation(client).error_code == "STALE_SUBSCRIPTION_REVIEW"
    assert provider.cancel_calls == []


def test_cancel_post_followed_by_new_payment_is_not_marked_verified(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    original = provider.cancel_subscription

    def cancel_then_new_payment(subscription_id):
        response = original(subscription_id)
        renewal(provider)
        provider.subscription["status"] = "active"
        return response

    monkeypatch.setattr(provider, "cancel_subscription", cancel_then_new_payment)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert (row.status, row.error_code) == ("review", "REFUND_NEWER_PAYMENT_REVIEW")
    assert provider.cancel_calls == ["sub_test"] and provider.subscription["status"] == "active"
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=datetime.now(UTC) + timedelta(days=1)
        )
        == 0
    )
    assert (
        event(
            client,
            "subscription.paid",
            "evt_payment_after_cancel",
            {"id": "sub_test", "mode": "test", "last_transaction_id": "tx_renewal"},
        ).status_code
        == 200
    )
    assert process(client, provider) == 1
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod))
        assert {paid.transaction_id: paid.status for paid in periods} == {
            "tx_test": "revoked",
            "tx_renewal": "active",
        }


def test_cancellation_rechecks_full_refund_before_provider_mutation(billing):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    provider.transactions["tx_test"].update(status="paid", refunded_amount=0)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert row.status == "retry" and row.attempts == 1
    assert provider.cancel_calls == []
    with client.app.state.session_factory() as session:
        assert session.scalar(select(PaidPeriod)).status == "revoked"


def test_old_refund_cannot_cancel_a_new_paid_period(billing):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    tx = renewal(provider)
    assert (
        event(
            client,
            "subscription.paid",
            "evt_new_paid",
            {"id": "sub_test", "mode": "test", "last_transaction_id": tx["id"]},
        ).status_code
        == 200
    )
    assert process(client, provider) == 1
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert (row.status, row.error_code) == ("review", "REFUND_NEWER_PAYMENT_REVIEW")
    assert provider.cancel_calls == [] and provider.subscription["status"] == "active"
    with client.app.state.session_factory() as session:
        periods = session.scalars(select(PaidPeriod))
        assert {paid.transaction_id: paid.status for paid in periods} == {
            "tx_test": "revoked",
            "tx_renewal": "active",
        }


def test_cancellation_rechecks_latest_transaction_immediately_before_post(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    original = provider.get_subscription
    reads = []

    def newer_payment_during_verification(subscription_id):
        reads.append(subscription_id)
        if len(reads) == 3:
            renewal(provider)
        return original(subscription_id)

    monkeypatch.setattr(provider, "get_subscription", newer_payment_during_verification)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    assert cancellation(client).error_code == "REFUND_NEWER_PAYMENT_REVIEW"
    assert provider.cancel_calls == [] and len(reads) == 3


def test_older_snapshot_after_new_payment_verification_cannot_trigger_cancel(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    old_snapshot = deepcopy(provider.subscription)
    old_snapshot["updated_at"] = datetime.now(UTC).isoformat()
    renewal(provider)
    newer_snapshot = deepcopy(provider.subscription)
    newer_snapshot["updated_at"] = (
        datetime.fromisoformat(old_snapshot["updated_at"]) + timedelta(seconds=1)
    ).isoformat()
    provider.subscription.update(old_snapshot)
    snapshots = iter([old_snapshot, newer_snapshot, old_snapshot])
    reads = []

    def returning_snapshots(subscription_id):
        reads.append(subscription_id)
        return deepcopy(next(snapshots))

    monkeypatch.setattr(provider, "get_subscription", returning_snapshots)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    row = cancellation(client)
    assert (row.status, row.error_code) == ("review", "REFUND_NEWER_PAYMENT_REVIEW")
    assert len(reads) == 2 and provider.cancel_calls == []
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=datetime.now(UTC) + timedelta(days=1)
        )
        == 0
    )
    assert len(reads) == 2 and provider.cancel_calls == []


@pytest.mark.parametrize("status", ["retry", "review", "verified"])
def test_duplicate_refunds_and_history_sweeps_never_reset_cancellation_intent(billing, status):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)
    next_attempt = datetime.now(UTC) + timedelta(days=1)
    with client.app.state.session_factory() as session:
        row = session.scalars(select(BillingCancellation)).one()
        row.status, row.attempts = status, 3
        row.error_code, row.next_attempt_at = "PRESERVED_AUDIT_ERROR", next_attempt
        original_id = row.id
        session.commit()
    assert refund(client, provider, "evt_full_refund_duplicate") == 1
    assert refund(client, provider, "evt_full_refund_duplicate") == 0
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 1
    assert process(client, provider) == 1
    assert scan_transactions(client.app.state.session_factory, provider)["queued"] == 0
    row = cancellation(client)
    assert (row.id, row.status, row.attempts, row.error_code) == (
        original_id,
        status,
        3,
        "PRESERVED_AUDIT_ERROR",
    )
    assert _as_utc(row.next_attempt_at) == next_attempt
    assert provider.cancel_calls == []


def test_eight_failed_cancellation_attempts_enter_review_without_infinite_posts(
    billing, monkeypatch
):
    client, provider = billing
    pay(client, provider)
    refund(client, provider)

    def failed_cancel(subscription_id):
        provider.cancel_calls.append(subscription_id)
        raise CreemError("offline provider unavailable")

    monkeypatch.setattr(provider, "cancel_subscription", failed_cancel)
    current = datetime.now(UTC) + timedelta(minutes=1)
    for attempt in range(1, 9):
        assert process_cancellations(client.app.state.session_factory, provider, now=current) == 1
        row = cancellation(client)
        assert row.attempts == attempt
        assert row.status == ("review" if attempt == 8 else "retry")
        assert _as_utc(row.next_attempt_at) > current
        current = _as_utc(row.next_attempt_at)
    assert len(provider.cancel_calls) == 8
    assert row.error_code == "CANCELLATION_CONFIRMATION_REQUIRED"
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=current + timedelta(days=1)
        )
        == 0
    )
