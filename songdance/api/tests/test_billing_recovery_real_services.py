"""Refund and reconciliation races on disposable PostgreSQL; provider stays offline."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import event, select

from app.models import BillingCancellation, BillingWebhookEvent, PaidPeriod, User
from app.services.billing import create_checkout
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import process_pending, sync_checkout, sync_transaction
from app.services.billing_reconciliation import scan_transactions
from app.services.entitlements import lock_usage_user
from tests.test_auth_ownership import auth_settings
from tests.test_auth_real_services import postgres as postgres
from tests.test_billing_recovery import renewal
from tests.test_creem_billing import FakeProvider
from tests.test_creem_real_services import database as database
from tests.test_creem_real_services import owner, signed_event

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)


def bound_provider(factory, tmp_path, *, paid=True):
    user_id = owner(factory)
    settings = auth_settings(tmp_path).model_copy(update={"creem_product_id": "prod_test"})
    provider = FakeProvider()
    with factory() as session:
        create_checkout(session, session.get(User, user_id), "key_one", settings, provider)
    provider.checkout["status"] = "completed"
    with factory.begin() as session:
        sync_checkout(session, provider, "ch_test")
    if paid:
        signed_event(factory)
        assert process_pending(factory, provider) == 1
    return user_id, provider


def refund_event(factory, provider, event_id="evt_refund"):
    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    return signed_event(
        factory,
        event_id=event_id,
        kind="refund.created",
        obj={
            "id": "refund_test",
            "mode": "test",
            "subscription": "sub_test",
            "transaction": "tx_test",
        },
    )


def test_competing_cancellation_workers_post_once_and_verify_once(database, tmp_path):
    _, engine, factory = database
    _, provider = bound_provider(factory, tmp_path)
    refund_event(factory, provider)
    assert process_pending(factory, provider) == 1
    barrier = Barrier(2)

    def synchronize_candidates(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT billing_cancellations.id ")
            and "billing_cancellations.status IN" in statement
            and "FOR UPDATE" not in statement
        ):
            barrier.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_candidates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: process_cancellations(factory, provider), range(2)))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_candidates)
    assert sorted(counts) == [0, 1] and provider.cancel_calls == ["sub_test"]
    with factory() as session:
        row = session.scalars(select(BillingCancellation)).one()
        assert (row.status, row.attempts, row.error_code) == ("verified", 1, None)
        assert session.scalar(select(PaidPeriod)).status == "revoked"


def test_concurrent_distinct_refund_events_persist_one_atomic_cancellation_intent(
    database, tmp_path
):
    _, engine, factory = database
    _, provider = bound_provider(factory, tmp_path)
    refund_event(factory, provider, "evt_refund_one")
    refund_event(factory, provider, "evt_refund_two")
    barrier = Barrier(2)

    def synchronize_candidates(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT billing_webhook_events.id ")
            and "FOR UPDATE" not in statement
        ):
            barrier.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_candidates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: process_pending(factory, provider), range(2)))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_candidates)
    assert sum(counts) == 2
    with factory() as session:
        paid = session.scalars(select(PaidPeriod)).one()
        intent = session.scalars(select(BillingCancellation)).one()
        assert paid.status == "revoked" and intent.paid_period_id == paid.id
        assert (intent.status, intent.attempts) == ("pending", 0)
        refunds = session.scalars(
            select(BillingWebhookEvent).where(BillingWebhookEvent.event_type == "refund.created")
        ).all()
        assert len(refunds) == 2 and all(row.status == "processed" for row in refunds)
    assert process_cancellations(factory, provider) == 1
    assert provider.cancel_calls == ["sub_test"]


def test_simultaneous_history_scans_share_one_durable_transaction_event(database, tmp_path):
    _, engine, factory = database
    _, provider = bound_provider(factory, tmp_path, paid=False)
    barrier = Barrier(2)

    def synchronize_initial_inbox_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT") and "billing_webhook_events.event_id =" in statement:
            if not conn.info.get("reconciliation_initial_read"):
                conn.info["reconciliation_initial_read"] = True
                barrier.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_initial_inbox_reads)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reports = list(pool.map(lambda _: scan_transactions(factory, provider), range(2)))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_initial_inbox_reads)
    assert all(report["scan_complete"] and report["scan_failed"] == 0 for report in reports)
    assert sum(report["queued"] for report in reports) == 1
    with factory() as session:
        row = session.scalars(select(BillingWebhookEvent)).one()
        assert (row.event_type, row.status, row.attempts) == (
            "reconciliation.transaction",
            "pending",
            0,
        )
        assert session.scalar(select(PaidPeriod)) is None
    assert process_pending(factory, provider) == 1
    with factory() as session:
        assert session.scalars(select(PaidPeriod.transaction_id)).all() == ["tx_test"]


def test_cancellation_waits_for_user_locked_renewal_and_never_cancels_new_period(
    database, tmp_path
):
    _, engine, factory = database
    user_id, provider = bound_provider(factory, tmp_path)
    refund_event(factory, provider)
    assert process_pending(factory, provider) == 1
    worker_waiting = Event()

    def observe_worker_lock_attempt(conn, cursor, statement, parameters, context, executemany):
        if "FROM users" in statement and "FOR NO KEY UPDATE" in statement:
            worker_waiting.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with factory.begin() as session:
            lock_usage_user(session, user_id)
            event.listen(engine, "before_cursor_execute", observe_worker_lock_attempt)
            try:
                waiting = pool.submit(process_cancellations, factory, provider)
                assert worker_waiting.wait(10), "cancellation did not attempt the user lock"
                assert provider.cancel_calls == [] and not waiting.done()
                tx = renewal(provider)
                assert sync_transaction(session, provider, "sub_test", tx["id"]) is False
            finally:
                event.remove(engine, "before_cursor_execute", observe_worker_lock_attempt)
        assert waiting.result(timeout=10) == 1
    assert provider.cancel_calls == [] and provider.subscription["status"] == "active"
    with factory() as session:
        row = session.scalars(select(BillingCancellation)).one()
        assert (row.status, row.error_code) == ("review", "REFUND_NEWER_PAYMENT_REVIEW")
        assert {
            paid.transaction_id: paid.status for paid in session.scalars(select(PaidPeriod))
        } == {
            "tx_test": "revoked",
            "tx_renewal": "active",
        }
    assert process_cancellations(factory, provider, now=datetime.now(UTC) + timedelta(days=1)) == 0
