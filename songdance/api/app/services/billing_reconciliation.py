"""Bounded provider history enumeration, feeding the durable verification inbox."""

import hashlib
import json
import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import BillingSubscription, BillingWebhookEvent
from app.services.billing import BillingMismatch, identifier, test_object
from app.services.creem_client import CreemClient

FINANCIAL_STATUSES = {"paid", "refunded", "partialRefund", "chargedBack"}
OTHER_STATUSES = {"pending", "uncollectible", "declined", "canceled", "void"}
PAGE_SIZE = 100


def _pagination(page: dict, requested: int) -> tuple[list[dict], int, int]:
    items, pagination = page.get("items"), page.get("pagination")
    if not isinstance(items, list) or len(items) > PAGE_SIZE or not isinstance(pagination, dict):
        raise BillingMismatch("invalid_transaction_pagination")
    total, pages = pagination.get("total_records"), pagination.get("total_pages")
    if (
        not {"total_records", "total_pages", "current_page", "next_page", "prev_page"}.issubset(
            pagination
        )
        or any(
            pagination.get(name) is not None and type(pagination[name]) is not int
            for name in ("next_page", "prev_page")
        )
        or type(total) is not int
        or total < 0
        or type(pages) is not int
        or pages < 0
        or pages != (total + PAGE_SIZE - 1) // PAGE_SIZE
        or pagination.get("current_page") != requested
        or type(pagination.get("current_page")) is not int
        or len(items) != max(0, min(PAGE_SIZE, total - (requested - 1) * PAGE_SIZE))
        or pagination.get("next_page") != (requested + 1 if requested < pages else None)
        or pagination.get("prev_page") != (requested - 1 if requested > 1 else None)
    ):
        raise BillingMismatch("invalid_transaction_pagination")
    return items, total, pages


def _queue_transaction(session: Session, value: dict) -> bool:
    tx_id, sub_id = identifier(value), identifier(value.get("subscription"))
    # Digest only financial facts: emails, addresses, descriptions and merchant
    # metadata never become inbox bodies. Facts are fetched again before projection.
    fields = {
        name: value.get(name)
        for name in (
            "id",
            "mode",
            "subscription",
            "customer",
            "type",
            "status",
            "amount",
            "currency",
            "amount_paid",
            "refunded_amount",
            "discount_amount",
            "period_start",
            "period_end",
        )
    }
    digest = hashlib.sha256(
        json.dumps(fields, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    event_id = "reconcile_" + digest
    binding = session.scalar(
        select(BillingSubscription.id).where(
            BillingSubscription.environment == "test",
            BillingSubscription.provider_id == sub_id,
        )
    )
    if session.get_bind().dialect.name == "sqlite":
        connection = session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    row = session.scalar(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.environment == "test",
            BillingWebhookEvent.event_id == event_id,
        )
    )
    if row is not None:
        if binding and row.error_code == "RECONCILIATION_UNBOUND":
            row.status, row.error_code = "pending", None
            row.next_attempt_at = datetime.now(UTC)
        return False
    try:
        with session.begin_nested():
            session.add(
                BillingWebhookEvent(
                    id=secrets.token_urlsafe(24),
                    environment="test",
                    event_id=event_id,
                    event_type="reconciliation.transaction",
                    body_hash=digest,
                    references=json.dumps(
                        {"object_id": tx_id, "subscription": sub_id, "transaction": tx_id}
                    ),
                    status="pending" if binding else "review",
                    attempts=0,
                    error_code=None if binding else "RECONCILIATION_UNBOUND",
                    next_attempt_at=datetime.now(UTC),
                )
            )
            session.flush()
    except IntegrityError:
        if (
            session.scalar(
                select(BillingWebhookEvent.id).where(
                    BillingWebhookEvent.environment == "test",
                    BillingWebhookEvent.event_id == event_id,
                )
            )
            is None
        ):
            raise
        return False
    return True


def scan_transactions(
    factory: sessionmaker[Session], provider: CreemClient, *, max_pages: int = 100
) -> dict[str, int | bool]:
    if type(max_pages) is not int or not 1 <= max_pages <= 1000:
        raise ValueError("max_pages must be between 1 and 1000")
    report: dict[str, int | bool] = {
        "pages": 0,
        "scanned": 0,
        "queued": 0,
        "unbound": 0,
        "scan_failed": 0,
        "scan_complete": False,
    }
    seen: set[str] = set()
    expected = None
    for page_number in range(1, max_pages + 1):
        try:
            items, total, pages = _pagination(
                provider.list_transactions(page_number=page_number, page_size=PAGE_SIZE),
                page_number,
            )
            if expected is not None and expected != (total, pages):
                raise BillingMismatch("transaction_history_changed")
            expected = (total, pages)
            # Validate the whole page before queuing any part of this page.
            identities = [identifier(test_object(item)) for item in items]
            if len(set(identities)) != len(identities) or seen.intersection(identities):
                raise BillingMismatch("transaction_history_repeated")
            report["pages"] += 1
            for tx in items:
                report["scanned"] += 1
                if tx.get("type") == "payment":
                    continue
                if tx.get("type") != "invoice" or tx.get("status") not in (
                    FINANCIAL_STATUSES | OTHER_STATUSES
                ):
                    raise BillingMismatch("unknown_transaction_contract")
                if tx["status"] not in FINANCIAL_STATUSES:
                    continue
                with factory() as session:
                    new = _queue_transaction(session, tx)
                    if not session.scalar(
                        select(BillingSubscription.id).where(
                            BillingSubscription.environment == "test",
                            BillingSubscription.provider_id == identifier(tx.get("subscription")),
                        )
                    ):
                        report["unbound"] += 1
                    session.commit()
                    report["queued"] += int(new)
            seen.update(identities)
            if page_number >= pages:
                report["scan_complete"] = True
                break
        except Exception:
            report["scan_failed"] += 1
            break
    return report
