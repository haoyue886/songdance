"""Verify authoritative provider objects and atomically project one durable event."""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    BillingSubscription,
    BillingWebhookEvent,
    CheckoutSession,
    PaidPeriod,
)
from app.observability import log_event
from app.services.billing import (
    BillingMismatch,
    account_for,
    check_product,
    identifier,
    test_object,
)
from app.services.creem_client import CreemClient
from app.services.entitlements import lock_usage_user
from app.services.paid_periods import grant_paid_period, set_paid_period_status
from app.services.usage import _as_utc


def receive_event(session: Session, raw: bytes, signature: str, secret: str) -> str:
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise BillingMismatch("invalid_signature")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise BillingMismatch("invalid_event")
    event_id = identifier(value.get("id"))
    kind = value.get("eventType")
    if not isinstance(kind, str) or not 1 <= len(kind) <= 64:
        raise BillingMismatch("invalid_event_type")
    obj = test_object(value.get("object"))
    refs = {"object_id": identifier(obj)}
    # Keep only references needed to re-fetch facts. No full body, email, or address.
    for field in ("request_id", "last_transaction_id", "transaction", "subscription"):
        if obj.get(field) is not None:
            refs[field] = identifier(obj[field])
    digest = hashlib.sha256(raw).hexdigest()
    previous = session.scalar(
        select(BillingWebhookEvent).where(
            BillingWebhookEvent.environment == "test", BillingWebhookEvent.event_id == event_id
        )
    )
    if previous is not None:
        if previous.body_hash != digest:
            raise BillingMismatch("event_id_conflict")
        return previous.id
    row = BillingWebhookEvent(
        id=secrets.token_urlsafe(24),
        environment="test",
        event_id=event_id,
        event_type=kind,
        body_hash=digest,
        references=json.dumps(refs),
        status="pending",
        attempts=0,
        next_attempt_at=datetime.now(UTC),
    )
    if session.get_bind().dialect.name == "sqlite":
        connection = session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN")
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        previous = session.scalar(
            select(BillingWebhookEvent).where(
                BillingWebhookEvent.environment == "test", BillingWebhookEvent.event_id == event_id
            )
        )
        if previous is None or previous.body_hash != digest:
            raise BillingMismatch("event_id_conflict") from None
        return previous.id
    return row.id


def iso_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise BillingMismatch("missing_provider_time")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise BillingMismatch("invalid_provider_time")
    return result.astimezone(UTC)


def transaction_time(value: object) -> datetime:
    # Official webhook examples use milliseconds. Ambiguous seconds are not guessed.
    if type(value) is not int or not 946684800000 <= value < 4102444800000:
        raise BillingMismatch("invalid_transaction_period")
    return datetime.fromtimestamp(value / 1000, UTC)


def sync_checkout(
    session: Session, provider: CreemClient, provider_id: str
) -> BillingSubscription | None:
    remote = test_object(provider.get_checkout(provider_id))
    if identifier(remote) != provider_id:
        raise BillingMismatch("checkout_identity_mismatch")
    local_id = identifier(remote.get("request_id"))
    local = session.get(CheckoutSession, local_id)
    if local is None or local.environment != "test":
        raise BillingMismatch("checkout_not_bound")
    lock_usage_user(session, local.user_id)
    session.refresh(local, with_for_update=True)
    if (
        local.provider_id not in {None, provider_id}
        or identifier(remote.get("product")) != local.product_id
        or remote.get("units", 1) != 1
    ):
        raise BillingMismatch("checkout_contract_mismatch")
    local.provider_id = provider_id
    if remote.get("status") == "expired":
        if local.status != "completed":
            local.status = "expired"
        return None
    if remote.get("status") != "completed":
        return None
    customer_id = identifier(remote.get("customer"))
    account = account_for(session, local.user_id)
    if account.customer_id not in {None, customer_id}:
        raise BillingMismatch("customer_binding_conflict")
    account.customer_id = customer_id
    sub_id = identifier(remote.get("subscription"))
    sub = test_object(provider.get_subscription(sub_id))
    if (
        identifier(sub) != sub_id
        or identifier(sub.get("customer")) != customer_id
        or identifier(sub.get("product")) != local.product_id
    ):
        raise BillingMismatch("subscription_binding_conflict")
    binding = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.environment == "test", BillingSubscription.provider_id == sub_id
        )
    )
    if binding is not None and (
        binding.user_id != local.user_id or binding.checkout_id != local.id
    ):
        raise BillingMismatch("subscription_binding_conflict")
    if binding is None:
        binding = BillingSubscription(
            id=secrets.token_urlsafe(24),
            user_id=local.user_id,
            environment="test",
            provider_id=sub_id,
            customer_id=customer_id,
            checkout_id=local.id,
            status="unknown",
            provider_updated_at=datetime(2000, 1, 1, tzinfo=UTC),
        )
        session.add(binding)
    _sync_subscription(binding, sub)
    local.status = "completed"
    local.error_code = None
    session.flush()
    return binding


def _sync_subscription(binding: BillingSubscription, remote: dict) -> None:
    if remote.get("status") not in {
        "active",
        "canceled",
        "unpaid",
        "paused",
        "trialing",
        "scheduled_cancel",
        "past_due",
        "expired",
    }:
        raise BillingMismatch("unknown_subscription_status")
    updated = iso_time(remote.get("updated_at"))
    if updated >= _as_utc(binding.provider_updated_at):
        binding.status = remote["status"]
        binding.provider_updated_at = updated


def sync_transaction(
    session: Session,
    provider: CreemClient,
    sub_id: str,
    transaction_id: str | None,
    *,
    event_kind: str | None = None,
) -> bool:
    binding = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.environment == "test", BillingSubscription.provider_id == sub_id
        )
    )
    if binding is None:
        raise BillingMismatch("subscription_not_bound")
    lock_usage_user(session, binding.user_id)
    session.refresh(binding, with_for_update=True)
    checkout = session.get(CheckoutSession, binding.checkout_id)
    remote = test_object(provider.get_subscription(sub_id))
    if (
        identifier(remote) != sub_id
        or identifier(remote.get("customer")) != binding.customer_id
        or identifier(remote.get("product")) != checkout.product_id
    ):
        raise BillingMismatch("subscription_binding_conflict")
    _sync_subscription(binding, remote)
    if transaction_id is None:
        return False  # active/canceled/past_due events are state only, never grants.
    tx = test_object(provider.get_transaction(transaction_id))
    if (
        identifier(tx) != transaction_id
        or identifier(tx.get("subscription")) != sub_id
        or (tx.get("customer") is not None and identifier(tx["customer"]) != binding.customer_id)
        or tx.get("type") != "invoice"
        or type(tx.get("amount")) is not int
        or tx["amount"] != checkout.amount_minor
        or tx.get("currency") != checkout.currency
        or tx.get("discount_amount", 0) not in {None, 0}
    ):
        raise BillingMismatch("transaction_contract_mismatch")
    # Existing financial history must still be refundable if a product is later archived/edited.
    existing = session.scalar(
        select(PaidPeriod).where(
            PaidPeriod.environment == "test", PaidPeriod.transaction_id == transaction_id
        )
    )
    if existing is None:
        check_product(provider.get_product(checkout.product_id), checkout)
    if tx.get("status") not in {"paid", "refunded", "partialRefund", "chargedBack"}:
        raise BillingMismatch("transaction_not_paid")
    if type(tx.get("amount_paid")) is not int or tx["amount_paid"] < checkout.amount_minor:
        raise BillingMismatch("missing_payment_evidence")
    if event_kind == "refund.created" and tx["status"] not in {"refunded", "partialRefund"}:
        raise BillingMismatch("refund_not_confirmed")
    if event_kind == "dispute.created" and tx["status"] != "chargedBack":
        raise BillingMismatch("dispute_not_confirmed")
    start, end = transaction_time(tx.get("period_start")), transaction_time(tx.get("period_end"))
    if end <= start:
        raise BillingMismatch("invalid_transaction_period")
    if remote.get("last_transaction_id") == transaction_id:
        if start != iso_time(remote.get("current_period_start_date")) or end != iso_time(
            remote.get("current_period_end_date")
        ):
            raise BillingMismatch("period_conflict")
    paid = grant_paid_period(
        session,
        user_id=binding.user_id,
        environment="test",
        transaction_id=transaction_id,
        subscription_id=sub_id,
        product_id=checkout.product_id,
        plan_version=checkout.plan_version,
        amount_minor=checkout.amount_minor,
        currency=checkout.currency,
        period_start=start,
        period_end=end,
        limit_seconds=checkout.limit_seconds,
        max_clip_seconds=checkout.max_clip_seconds,
    )
    if tx["status"] == "refunded":
        if (
            type(tx.get("amount_paid")) is not int
            or tx["amount_paid"] <= 0
            or tx.get("refunded_amount") != tx["amount_paid"]
        ):
            raise BillingMismatch("refund_requires_review")
        set_paid_period_status(
            session,
            user_id=binding.user_id,
            environment="test",
            transaction_id=paid.transaction_id,
            status="revoked",
        )
    elif tx["status"] == "chargedBack":
        account_for(session, binding.user_id).blocked = True
        set_paid_period_status(
            session,
            user_id=binding.user_id,
            environment="test",
            transaction_id=paid.transaction_id,
            status="frozen",
        )
    elif tx["status"] == "partialRefund":
        # Retain minutes unchanged; explicit review status is persisted by the event processor.
        log_event("billing_partial_refund_review")
        return True
    return False


def apply_event(session: Session, event: BillingWebhookEvent, provider: CreemClient) -> None:
    refs = json.loads(event.references)
    kind = event.event_type
    if kind == "checkout.completed":
        sync_checkout(session, provider, refs["object_id"])
    elif kind in {
        "subscription.paid",
        "subscription.active",
        "subscription.canceled",
        "subscription.scheduled_cancel",
        "subscription.past_due",
        "subscription.unpaid",
        "subscription.expired",
        "subscription.trialing",
        "subscription.paused",
        "subscription.update",
    }:
        tx_id = refs.get("last_transaction_id") if kind == "subscription.paid" else None
        if kind == "subscription.paid" and not tx_id:
            raise BillingMismatch("missing_paid_transaction")
        if sync_transaction(session, provider, refs["object_id"], tx_id):
            event.status = "review"
            event.error_code = "PARTIAL_REFUND_REVIEW"
            return
    elif kind in {"refund.created", "dispute.created"}:
        review = sync_transaction(
            session,
            provider,
            identifier(refs.get("subscription")),
            identifier(refs.get("transaction")),
            event_kind=kind,
        )
        if review:
            event.status = "review"
            event.error_code = "PARTIAL_REFUND_REVIEW"
            return
    else:
        event.status = "review"
        event.error_code = "UNHANDLED_EVENT"
        return
    event.status = "processed"
    event.error_code = None


def process_pending(
    factory: sessionmaker[Session], provider: CreemClient, *, limit: int = 100
) -> int:
    now = datetime.now(UTC)
    with factory() as session:
        ids = session.scalars(
            select(BillingWebhookEvent.id)
            .where(
                BillingWebhookEvent.environment == "test",
                BillingWebhookEvent.status.in_(["pending", "retry"]),
                BillingWebhookEvent.next_attempt_at <= now,
            )
            .order_by(BillingWebhookEvent.created_at)
            .limit(limit)
        ).all()
    processed = 0
    for event_id in ids:
        with factory() as session:
            event = session.scalar(
                select(BillingWebhookEvent)
                .where(
                    BillingWebhookEvent.id == event_id,
                    BillingWebhookEvent.status.in_(["pending", "retry"]),
                    BillingWebhookEvent.next_attempt_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
            if event is None:
                continue
            event.attempts += 1
            try:
                with session.begin_nested():
                    apply_event(session, event, provider)
                    session.flush()
            except Exception:
                event.status = "review" if event.attempts >= 8 else "retry"
                event.error_code = "PROVIDER_OR_BINDING_REVIEW"
                event.next_attempt_at = now + timedelta(
                    seconds=min(3600, 30 * 2 ** min(event.attempts, 7))
                )
                log_event("billing_event_retry", attempt=event.attempts)
            session.commit()
            processed += 1
    return processed


def reconcile_known(factory: sessionmaker[Session], provider: CreemClient) -> dict[str, int]:
    """Recover known checkouts and latest payments; audit each known historical transaction.

    Not a claim of complete provider transaction enumeration: missing historical cycles
    without a known ID remain a dashboard/support reconciliation item.
    """
    with factory() as session:
        checkouts = session.scalars(
            select(CheckoutSession.provider_id).where(
                CheckoutSession.environment == "test", CheckoutSession.provider_id.is_not(None)
            )
        ).all()
        subscriptions = session.scalars(
            select(BillingSubscription.provider_id).where(BillingSubscription.environment == "test")
        ).all()
        history = session.execute(
            select(PaidPeriod.subscription_id, PaidPeriod.transaction_id).where(
                PaidPeriod.environment == "test"
            )
        ).all()
    completed = failed = 0
    for checkout_id in checkouts:
        try:
            with factory() as session:
                sync_checkout(session, provider, checkout_id)
                session.commit()
            completed += 1
        except Exception:
            failed += 1
    with factory() as session:
        subscriptions = session.scalars(
            select(BillingSubscription.provider_id).where(BillingSubscription.environment == "test")
        ).all()
    for sub_id in subscriptions:
        try:
            remote = test_object(provider.get_subscription(sub_id))
            tx_id = remote.get("last_transaction_id")
            with factory() as session:
                sync_transaction(session, provider, sub_id, identifier(tx_id) if tx_id else None)
                session.commit()
            completed += 1
        except Exception:
            failed += 1
    for sub_id, tx_id in history:
        try:
            with factory() as session:
                sync_transaction(session, provider, sub_id, tx_id)
                session.commit()
            completed += 1
        except Exception:
            failed += 1
    log_event("billing_reconciliation", completed=completed, failed=failed)
    return {"completed": completed, "failed": failed}
