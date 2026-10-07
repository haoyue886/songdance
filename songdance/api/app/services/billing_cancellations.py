"""Refund cancellation intents survive provider failures and process restarts."""

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import BillingCancellation, BillingSubscription, PaidPeriod
from app.observability import log_event
from app.services.billing import BillingMismatch
from app.services.creem_client import CreemClient
from app.services.entitlements import lock_usage_user
from app.services.usage import _as_utc


def request_refund_cancellation(session: Session, paid: PaidPeriod) -> None:
    # Projection already holds the user's admission lock. Never erase a completed
    # or reviewed intent on duplicate webhooks or the next reconciliation sweep.
    existing = session.scalar(
        select(BillingCancellation.id).where(
            BillingCancellation.environment == paid.environment,
            BillingCancellation.transaction_id == paid.transaction_id,
        )
    )
    if existing is None:
        session.add(
            BillingCancellation(
                id=secrets.token_urlsafe(24),
                user_id=paid.user_id,
                environment=paid.environment,
                paid_period_id=paid.id,
                subscription_id=paid.subscription_id,
                transaction_id=paid.transaction_id,
                status="pending",
                attempts=0,
                next_attempt_at=datetime.now(UTC),
            )
        )


def _cancel_refunded_subscription(
    session: Session, row: BillingCancellation, provider: CreemClient
) -> None:
    from app.services.billing_events import checked_subscription, iso_time, sync_transaction

    def current_subscription(binding: BillingSubscription) -> dict:
        remote = checked_subscription(session, provider, binding)
        if iso_time(remote["updated_at"]) < _as_utc(binding.provider_updated_at):
            raise BillingMismatch("stale_subscription_state")
        return remote

    lock_usage_user(session, row.user_id)
    paid = session.get(PaidPeriod, row.paid_period_id)
    binding = session.scalar(
        select(BillingSubscription).where(
            BillingSubscription.environment == row.environment,
            BillingSubscription.provider_id == row.subscription_id,
        )
    )
    if (
        row.environment != "test"
        or paid is None
        or binding is None
        or paid.status != "revoked"
        or paid.environment != row.environment
        or paid.user_id != row.user_id
        or paid.transaction_id != row.transaction_id
        or paid.subscription_id != row.subscription_id
        or binding.user_id != row.user_id
    ):
        raise BillingMismatch("cancellation_binding_mismatch")
    if session.scalar(
        select(PaidPeriod.id)
        .where(
            PaidPeriod.environment == row.environment,
            PaidPeriod.user_id == row.user_id,
            PaidPeriod.subscription_id == row.subscription_id,
            PaidPeriod.transaction_id != row.transaction_id,
            PaidPeriod.period_start > paid.period_start,
            PaidPeriod.status.in_(["active", "frozen"]),
        )
        .limit(1)
    ):
        row.status, row.error_code = "review", "REFUND_NEWER_PAYMENT_REVIEW"
        return
    remote = current_subscription(binding)
    if remote.get("last_transaction_id") != row.transaction_id:
        row.status, row.error_code = "review", "REFUND_NEWER_PAYMENT_REVIEW"
        return
    if sync_transaction(
        session,
        provider,
        row.subscription_id,
        row.transaction_id,
        event_kind="refund.created",
        expected_latest_transaction=row.transaction_id,
    ):
        raise BillingMismatch("refund_requires_review")
    # Re-read immediately before mutation: the earlier refund may now be history.
    remote = current_subscription(binding)
    if remote.get("last_transaction_id") != row.transaction_id:
        row.status, row.error_code = "review", "REFUND_NEWER_PAYMENT_REVIEW"
        return
    if remote["status"] not in {"canceled", "scheduled_cancel"}:
        provider.cancel_subscription(row.subscription_id)
        remote = current_subscription(binding)
    if remote.get("last_transaction_id") != row.transaction_id:
        row.status, row.error_code = "review", "REFUND_NEWER_PAYMENT_REVIEW"
        return
    if remote["status"] not in {"canceled", "scheduled_cancel"}:
        raise BillingMismatch("cancellation_not_confirmed")
    row.status, row.error_code = "verified", None


def process_cancellations(
    factory: sessionmaker[Session],
    provider: CreemClient,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(UTC)
    with factory() as session:
        ids = session.scalars(
            select(BillingCancellation.id)
            .where(
                BillingCancellation.environment == "test",
                BillingCancellation.status.in_(["pending", "retry"]),
                BillingCancellation.next_attempt_at <= current,
            )
            .order_by(BillingCancellation.created_at)
            .limit(limit)
        ).all()
    handled = 0
    for identifier in ids:
        with factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.scalar(
                select(BillingCancellation)
                .where(
                    BillingCancellation.id == identifier,
                    BillingCancellation.status.in_(["pending", "retry"]),
                    BillingCancellation.next_attempt_at <= current,
                )
                .with_for_update(skip_locked=True)
            )
            if row is None:
                continue
            row.attempts += 1
            try:
                with session.begin_nested():
                    _cancel_refunded_subscription(session, row, provider)
                    session.flush()
            except BillingMismatch as error:
                if str(error) in {"refund_newer_payment_review", "stale_subscription_state"}:
                    # This decision must survive the savepoint rollback. A later
                    # stale read must not put a newer payment at risk on retry.
                    row.status = "review"
                    row.error_code = (
                        "REFUND_NEWER_PAYMENT_REVIEW"
                        if str(error) == "refund_newer_payment_review"
                        else "STALE_SUBSCRIPTION_REVIEW"
                    )
                else:
                    _retry(row, current)
            except Exception:
                _retry(row, current)
            from app.services.account_deletion_billing import persist_observed_obligations

            persist_observed_obligations(session)
            session.commit()
            log_event("billing_cancellation", status=row.status, attempt=row.attempts)
            handled += 1
    return handled


def _retry(row: BillingCancellation, current: datetime) -> None:
    row.status = "review" if row.attempts >= 8 else "retry"
    row.error_code = "CANCELLATION_CONFIRMATION_REQUIRED"
    row.next_attempt_at = current + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
