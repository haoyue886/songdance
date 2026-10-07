"""Worker scheduling and failure exit semantics without an external payment service."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import app.jobs.billing as worker
from app.models import BillingCancellation, PaidPeriod
from app.services.billing_cancellations import process_cancellations
from app.services.billing_events import process_pending
from tests.test_creem_billing import billing as billing
from tests.test_creem_billing import event, pay


def configure(monkeypatch, client, provider, arguments):
    monkeypatch.setattr("sys.argv", ["billing", *arguments])
    monkeypatch.setattr(worker, "get_settings", lambda: client.app.state.settings)
    monkeypatch.setattr(worker, "create_db_engine", lambda _: client.app.state.engine)
    monkeypatch.setattr(worker, "CreemClient", lambda _: provider)
    monkeypatch.setattr(worker, "configure_logging", lambda: None)


def test_once_processes_refund_and_cancellation_in_same_cycle(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    event(
        client,
        "refund.created",
        "refund_worker",
        {
            "id": "refund_test",
            "mode": "test",
            "subscription": "sub_test",
            "transaction": "tx_test",
        },
    )
    configure(monkeypatch, client, provider, ["--once"])
    worker.main()
    with client.app.state.session_factory() as session:
        assert session.scalar(select(BillingCancellation)).status == "verified"
    assert provider.cancel_calls == ["sub_test"]


def test_loop_reconciliation_respects_interval(billing, monkeypatch):
    client, provider = billing
    configure(monkeypatch, client, provider, ["--loop", "--reconcile"])
    clock = {"now": 0, "cycles": 0}
    calls = []
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(worker, "process_pending", lambda *_: 0)
    monkeypatch.setattr(worker, "process_cancellations", lambda *_: 0)

    def reconcile(*_, **kwargs):
        calls.append((clock["now"], kwargs))
        return {"failed": 0, "scan_failed": 0, "scan_complete": True}

    def next_cycle(_):
        clock["cycles"] += 1
        if clock["cycles"] == 3:
            raise InterruptedError("bounded worker test")
        clock["now"] += 15 if clock["cycles"] == 1 else 86400

    monkeypatch.setattr(worker, "reconcile_known", reconcile)
    monkeypatch.setattr(worker.time, "sleep", next_cycle)
    with pytest.raises(InterruptedError, match="bounded worker"):
        worker.main()
    assert [time for time, _ in calls] == [0, 86415]
    assert all(options == {"max_pages": 100} for _, options in calls)


@pytest.mark.parametrize(
    "report",
    [
        {"failed": 0, "scan_failed": 0, "scan_complete": False},
        {"failed": 1, "scan_failed": 0, "scan_complete": True},
        {"failed": 0, "scan_failed": 1, "scan_complete": False},
    ],
)
def test_incomplete_once_reconciliation_fails_scheduler(billing, monkeypatch, report):
    client, provider = billing
    configure(monkeypatch, client, provider, ["--once", "--reconcile"])
    monkeypatch.setattr(worker, "reconcile_known", lambda *_, **__: report)
    with pytest.raises(SystemExit, match="incomplete"):
        worker.main()


def test_manual_cancellation_replay_keeps_attempt_history(billing, monkeypatch):
    client, provider = billing
    pay(client, provider)
    provider.transactions["tx_test"].update(status="refunded", refunded_amount=990)
    event(
        client,
        "refund.created",
        "refund_replay",
        {
            "id": "refund_test",
            "mode": "test",
            "subscription": "sub_test",
            "transaction": "tx_test",
        },
    )
    process_pending(client.app.state.session_factory, provider)
    with client.app.state.session_factory.begin() as session:
        row = session.scalar(select(BillingCancellation))
        row.id = "-cancel-replay-leading-hyphen"
        row.status, row.attempts = "review", 8
        row.next_attempt_at = datetime.now(UTC)
        row_id = row.id
    configure(monkeypatch, client, provider, ["--once", f"--replay-cancellation-id={row_id}"])
    worker.main()
    with client.app.state.session_factory() as session:
        row = session.get(BillingCancellation, row_id)
        assert (row.status, row.attempts) == ("verified", 9)


def test_verified_later_payment_blocks_conflicting_equal_timestamp_subscription(
    billing, monkeypatch
):
    from tests.test_billing_recovery import refund, renewal

    client, provider = billing
    pay(client, provider)
    old = deepcopy(provider.subscription)
    renewal(provider)
    event(
        client,
        "subscription.paid",
        "evt_renewal_worker",
        {
            "id": "sub_test",
            "mode": "test",
            "last_transaction_id": "tx_renewal",
        },
    )
    process_pending(client.app.state.session_factory, provider)
    refund(client, provider)
    with client.app.state.session_factory() as session:
        assert len(session.scalars(select(PaidPeriod)).all()) == 2
    old["updated_at"] = provider.subscription["updated_at"]
    calls = []

    def stale_subscription(_):
        calls.append("get")
        return deepcopy(old)

    monkeypatch.setattr(provider, "get_subscription", stale_subscription)
    assert process_cancellations(client.app.state.session_factory, provider) == 1
    assert provider.cancel_calls == [] and calls == []
    with client.app.state.session_factory() as session:
        row = session.scalar(select(BillingCancellation))
        assert (row.status, row.error_code) == ("review", "REFUND_NEWER_PAYMENT_REVIEW")
        new = session.scalar(select(PaidPeriod).where(PaidPeriod.transaction_id == "tx_renewal"))
        assert new.status == "active"
    assert (
        process_cancellations(
            client.app.state.session_factory, provider, now=datetime.now(UTC) + timedelta(days=2)
        )
        == 0
    )
    assert provider.cancel_calls == []
