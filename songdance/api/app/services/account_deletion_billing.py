"""Verify all bound billing obligations before account cleanup can begin."""

import secrets
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountDeletion,
    AccountDeletionSubscription,
    BillingAccount,
    BillingSubscription,
    CheckoutSession,
    PaidPeriod,
)
from app.services.billing import (
    CUSTOMER_BINDING_CONFLICT,
    BillingMismatch,
    identifier,
    test_object,
)
from app.services.billing_events import checked_subscription, iso_time, sync_checkout
from app.services.billing_reconciliation import _pagination
from app.services.creem_client import CreemClient
from app.services.usage import _as_utc


def verify_stopped_billing(
    session: Session, deletion: AccountDeletion, provider: CreemClient | None
) -> None:
    # Terminal historical checkouts can still carry unresolved ownership
    # conflicts; their financial obligations must survive account cleanup.
    if session.scalar(
        select(CheckoutSession.id)
        .where(
            CheckoutSession.user_id == deletion.user_id,
            CheckoutSession.error_code == CUSTOMER_BINDING_CONFLICT,
        )
        .limit(1)
    ):
        raise BillingMismatch("DELETION_CUSTOMER_CONFLICT")
    checkouts = session.scalars(
        select(CheckoutSession).where(
            CheckoutSession.user_id == deletion.user_id,
            CheckoutSession.status.in_(["creating", "pending", "uncertain"]),
        )
    ).all()
    for checkout in checkouts:
        if checkout.environment != "test":
            raise BillingMismatch("DELETION_UNVERIFIED_ENVIRONMENT")
        if provider is None or not checkout.provider_id:
            raise RuntimeError("PAYMENT_CONFIRMATION_REQUIRED")
        sync_checkout(session, provider, checkout.provider_id)
        if checkout.status not in {"completed", "expired", "failed"}:
            raise RuntimeError("PAYMENT_CONFIRMATION_REQUIRED")
    accounts = session.scalars(
        select(BillingAccount).where(BillingAccount.user_id == deletion.user_id)
    ).all()
    bindings = session.scalars(
        select(BillingSubscription).where(BillingSubscription.user_id == deletion.user_id)
    ).all()
    paid = session.scalars(select(PaidPeriod).where(PaidPeriod.user_id == deletion.user_id)).all()
    if any(item.environment != "test" for item in [*accounts, *bindings, *paid]):
        raise BillingMismatch("DELETION_UNVERIFIED_ENVIRONMENT")
    by_id = {item.provider_id: item for item in bindings}
    if any(item.subscription_id not in by_id for item in paid):
        raise BillingMismatch("DELETION_UNBOUND_PAYMENT")
    customers = {item.customer_id for item in accounts if item.customer_id}
    if any(binding.customer_id not in customers for binding in bindings):
        raise BillingMismatch("DELETION_CUSTOMER_CONFLICT")
    if (customers or bindings) and provider is None:
        raise RuntimeError("BILLING_UNAVAILABLE")
    listed: set[str] = set()
    for customer_id in customers:
        previous = None
        for page_number in range(1, 101):
            items, total, pages = _pagination(
                provider.list_customer_subscriptions(
                    customer_id, page_number=page_number, page_size=100
                ),
                page_number,
            )
            if previous is not None and previous != (total, pages):
                raise RuntimeError("DELETION_BILLING_CHANGED")
            previous = (total, pages)
            for item in items:
                remote = test_object(item)
                sub_id = identifier(remote)
                if sub_id in listed:
                    raise BillingMismatch("DELETION_SUBSCRIPTION_REPEATED")
                binding = by_id.get(sub_id)
                if (
                    binding is None
                    or identifier(remote.get("customer")) != customer_id
                    or binding.customer_id != customer_id
                ):
                    raise BillingMismatch("DELETION_UNBOUND_SUBSCRIPTION")
                listed.add(sub_id)
            if page_number >= pages:
                break
        else:
            raise RuntimeError("DELETION_SCAN_INCOMPLETE")
    if not set(by_id).issubset(listed):
        raise BillingMismatch("DELETION_SUBSCRIPTION_MISSING")
    for binding in bindings:
        step = session.scalar(
            select(AccountDeletionSubscription).where(
                AccountDeletionSubscription.deletion_id == deletion.id,
                AccountDeletionSubscription.environment == "test",
                AccountDeletionSubscription.subscription_id == binding.provider_id,
            )
        )
        if step is None:
            step = AccountDeletionSubscription(
                id=secrets.token_urlsafe(24),
                deletion_id=deletion.id,
                environment="test",
                subscription_id=binding.provider_id,
                status="pending",
            )
            session.add(step)
        remote = checked_subscription(session, provider, binding)
        updated = iso_time(remote["updated_at"])
        if updated < _as_utc(binding.provider_updated_at) or (
            step.provider_updated_at and updated < _as_utc(step.provider_updated_at)
        ):
            raise BillingMismatch("DELETION_STALE_SUBSCRIPTION")
        if remote["status"] not in {"canceled", "scheduled_cancel"}:
            provider.cancel_subscription(binding.provider_id)
            remote = checked_subscription(session, provider, binding)
            if iso_time(remote["updated_at"]) < updated:
                raise BillingMismatch("DELETION_STALE_SUBSCRIPTION")
        if remote["status"] not in {"canceled", "scheduled_cancel"}:
            raise RuntimeError("CANCELLATION_CONFIRMATION_REQUIRED")
        step.status = "verified"
        step.provider_updated_at = iso_time(remote["updated_at"])
        step.verified_at = datetime.now(UTC)


def note_subscription_change(
    session: Session, user_id: str, subscription_status: str, *, observed: bool = True
) -> None:
    if subscription_status in {"canceled", "scheduled_cancel"}:
        return
    deletion = session.scalar(select(AccountDeletion).where(AccountDeletion.user_id == user_id))
    if deletion and (deletion.phase == "cleanup" or deletion.status == "completed"):
        if observed:
            session.info.setdefault("account_billing_reactivated", set()).add(user_id)
        deletion.phase, deletion.status = "billing", "pending"
        deletion.completed_at = None
        deletion.error_code = "DELETION_NEW_BILLING"
        deletion.next_attempt_at = datetime.now(UTC)


def note_customer_binding_conflict(session: Session, user_id: str) -> None:
    deletion = session.scalar(select(AccountDeletion).where(AccountDeletion.user_id == user_id))
    if deletion is None:
        return
    if deletion.phase == "cleanup" or deletion.status == "completed":
        deletion.phase, deletion.status = "billing", "review"
        deletion.error_code = "DELETION_CUSTOMER_CONFLICT"
        deletion.completed_at = None
        deletion.next_attempt_at = datetime.now(UTC)


def persist_observed_obligations(session: Session) -> None:
    from app.services.entitlements import lock_usage_user

    # A failed financial projection must not discard a separately verified
    # reactivation. Reapply only this cancellation obligation after rollback.
    users = session.info.pop("account_billing_reactivated", set())
    for user_id in users:
        lock_usage_user(session, user_id)
        note_subscription_change(session, user_id, "active", observed=False)
