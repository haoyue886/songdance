"""Checkout intents survive unknown provider outcomes. No browser field grants access."""

import secrets
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingAccount, BillingSubscription, CheckoutSession, PaidPeriod, User
from app.services.billing_plan import CURRENCY, MAX_CLIP_SECONDS, PAID_SECONDS, PRICE_MINOR
from app.services.creem_client import CreemClient, validate_hosted_url
from app.services.entitlements import lock_usage_user
from app.settings import Settings


class BillingMismatch(ValueError):
    """Provider facts conflict with the server's stored commercial contract."""


def identifier(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("id")
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise BillingMismatch("invalid_reference")
    if any(not (char.isalnum() or char in "_-.") for char in value):
        raise BillingMismatch("invalid_reference")
    return value


def test_object(value: object) -> dict:
    if not isinstance(value, dict) or value.get("mode") not in {"test", "sandbox"}:
        raise BillingMismatch("environment_mismatch")
    identifier(value.get("id"))
    return value


def provider_url(value: object) -> str:
    return validate_hosted_url(value)


def check_product(product: dict, checkout: CheckoutSession) -> None:
    test_object(product)
    if (
        identifier(product) != checkout.product_id
        or type(product.get("price")) is not int
        or product["price"] != checkout.amount_minor
        or product.get("currency") != checkout.currency
        or product.get("billing_type") != "recurring"
        or product.get("billing_period") != "every-month"
        or product.get("trial_period_days")
        or product.get("trial_price")
        or product.get("usage_prices")
    ):
        raise BillingMismatch("product_mismatch")


def account_for(session: Session, user_id: str) -> BillingAccount:
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.user_id == user_id, BillingAccount.environment == "test"
        )
    )
    if account is None:
        account = BillingAccount(
            id=secrets.token_urlsafe(24), user_id=user_id, environment="test", blocked=False
        )
        session.add(account)
        session.flush()
    return account


def checkout_response(checkout: CheckoutSession) -> dict[str, object]:
    return {
        "id": checkout.id,
        "status": checkout.status,
        "checkout_url": checkout.checkout_url if checkout.status == "pending" else None,
        "sync_state": "payment_confirming" if checkout.status != "expired" else "expired",
    }


def create_checkout(
    session: Session, user: User, key: str, settings: Settings, provider: CreemClient
) -> dict[str, object]:
    lock_usage_user(session, user.id)
    account = account_for(session, user.id)
    if account.blocked:
        raise HTTPException(409, detail={"code": "BILLING_REVIEW_REQUIRED"})
    # Repeated keys never start another provider request, including expired/uncertain intents.
    repeated = session.scalar(
        select(CheckoutSession).where(
            CheckoutSession.user_id == user.id,
            CheckoutSession.environment == "test",
            CheckoutSession.idempotency_key == key,
        )
    )
    if repeated:
        return checkout_response(repeated)
    open_checkout = session.scalar(
        select(CheckoutSession).where(
            CheckoutSession.user_id == user.id,
            CheckoutSession.environment == "test",
            CheckoutSession.status.in_(["creating", "pending", "uncertain"]),
        )
    )
    if open_checkout:
        return checkout_response(open_checkout)
    if session.scalar(
        select(BillingSubscription.id)
        .where(
            BillingSubscription.user_id == user.id,
            BillingSubscription.environment == "test",
            BillingSubscription.status != "canceled",
        )
        .limit(1)
    ) or session.scalar(
        select(PaidPeriod.id)
        .where(
            PaidPeriod.user_id == user.id,
            PaidPeriod.environment == "test",
            PaidPeriod.period_end > datetime.now(UTC),
        )
        .limit(1)
    ):
        raise HTTPException(409, detail={"code": "SUBSCRIPTION_EXISTS"})
    checkout = CheckoutSession(
        id=secrets.token_urlsafe(24),
        user_id=user.id,
        environment="test",
        idempotency_key=key,
        product_id=settings.creem_product_id,
        plan_version=settings.creem_plan_version,
        amount_minor=PRICE_MINOR,
        currency=CURRENCY,
        limit_seconds=PAID_SECONDS,
        max_clip_seconds=MAX_CLIP_SECONDS,
        success_url=settings.creem_success_url,
        status="creating",
        created_at=datetime.now(UTC),
    )
    session.add(checkout)
    customer_id = account.customer_id
    session.commit()  # durable before any external mutation
    post_started = False
    try:
        check_product(provider.get_product(checkout.product_id), checkout)
        post_started = True
        response = test_object(
            provider.create_checkout(
                request_id=checkout.id,
                product_id=checkout.product_id,
                success_url=checkout.success_url,
                customer_id=customer_id,
            )
        )
        if (
            response.get("request_id") != checkout.id
            or identifier(response.get("product")) != checkout.product_id
            or response.get("status") not in {"pending", "processing", "completed"}
        ):
            raise BillingMismatch("checkout_mismatch")
        link = provider_url(response.get("checkout_url"))
        session.refresh(checkout, with_for_update=True)
        if checkout.provider_id not in {None, response["id"]}:
            raise BillingMismatch("checkout_identity_conflict")
        checkout.provider_id = response["id"]
        if checkout.status not in {"completed", "expired"}:
            checkout.status = "pending"
            checkout.checkout_url = link
        session.commit()
    except Exception:
        session.rollback()
        session.refresh(checkout, with_for_update=True)
        if checkout.status == "creating":
            checkout.status = "uncertain" if post_started else "failed"
            checkout.error_code = (
                "CHECKOUT_CONFIRMATION_REQUIRED" if post_started else "PRODUCT_VERIFICATION_FAILED"
            )
        session.commit()
        # request_id is tracking only in the documented API, not proven POST idempotency.
        # Never retry POST automatically after timeout, network loss, or process death.
    return checkout_response(checkout)


def create_portal(session: Session, user: User, provider: CreemClient) -> str:
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.user_id == user.id, BillingAccount.environment == "test"
        )
    )
    if account is None or account.customer_id is None:
        raise HTTPException(409, detail={"code": "BILLING_CUSTOMER_NOT_READY"})
    return provider_url(provider.create_portal(account.customer_id)["customer_portal_link"])


def billing_state(session: Session, user_id: str) -> dict[str, object]:
    account = session.scalar(
        select(BillingAccount).where(
            BillingAccount.user_id == user_id, BillingAccount.environment == "test"
        )
    )
    recent = session.scalar(
        select(CheckoutSession)
        .where(CheckoutSession.user_id == user_id, CheckoutSession.environment == "test")
        .order_by(CheckoutSession.created_at.desc())
        .limit(1)
    )
    sub = session.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.user_id == user_id, BillingSubscription.environment == "test")
        .order_by(BillingSubscription.created_at.desc())
        .limit(1)
    )
    state = "ready"
    if recent is not None and recent.status in {"creating", "pending", "uncertain"}:
        state = "payment_confirming"
    elif recent is not None and recent.status == "completed":
        linked_subscription = session.scalar(
            select(BillingSubscription).where(
                BillingSubscription.environment == "test",
                BillingSubscription.checkout_id == recent.id,
                BillingSubscription.user_id == user_id,
            )
        )
        paid = session.scalar(
            select(PaidPeriod.id)
            .where(
                PaidPeriod.user_id == user_id,
                PaidPeriod.environment == "test",
                PaidPeriod.subscription_id == linked_subscription.provider_id
                if linked_subscription
                else PaidPeriod.id.is_(None),
            )
            .limit(1)
        )
        if not paid:
            state = "payment_confirming"
    if account and account.blocked:
        state = "review_required"
    return {
        "sync_state": state,
        "checkout_status": recent.status if recent else None,
        "checkout_key": recent.idempotency_key if recent else None,
        "subscription_status": sub.status if sub else None,
        "portal_available": bool(account and account.customer_id),
    }
