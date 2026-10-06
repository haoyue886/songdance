from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import CheckoutSession, PaidPeriod
from app.services.billing import billing_state
from tests.test_creem_billing import billing as billing
from tests.test_creem_billing import checkout, pay


def test_public_config_drives_disabled_and_test_commercial_contract(api_client):
    client, _, _ = api_client
    response = client.get("/billing/config")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "usage_enabled": False,
        "reliable_queue_enabled": False,
        "checkout_enabled": False,
        "mode": "unavailable",
        "pro": {
            "price_minor": 990,
            "currency": "USD",
            "seconds": 1800,
            "max_clip_seconds": 90,
            "min_charge_seconds": 15,
        },
        "free": {"monthly_jobs": 1, "max_clip_seconds": 90},
        "guest": {"max_clip_seconds": 90},
        "guest_usage_enabled": False,
        "retention_hours": 24,
        "support_email": None,
    }


def test_config_matches_checkout_snapshot_without_exposing_provider_secrets(billing):
    client, _ = billing
    config = client.get("/billing/config").json()
    assert config["checkout_enabled"] is True and config["mode"] == "test"
    assert config["guest"]["max_clip_seconds"] == 30
    checkout(client)
    with client.app.state.session_factory() as session:
        intent = session.scalar(select(CheckoutSession))
        assert intent.amount_minor == config["pro"]["price_minor"]
        assert intent.limit_seconds == config["pro"]["seconds"]
        assert intent.max_clip_seconds == config["pro"]["max_clip_seconds"]
    assert "creem" not in str(config).lower()
    client.app.state.settings.environment = "production"
    assert client.get("/billing/config").json()["checkout_enabled"] is False


def test_new_pending_checkout_does_not_inherit_old_paid_confirmation(billing):
    client, provider = billing
    pay(client, provider)
    with client.app.state.session_factory() as session:
        old = session.scalar(select(CheckoutSession))
        paid = session.scalar(select(PaidPeriod))
        paid.period_end = datetime.now(UTC) - timedelta(days=1)
        new = CheckoutSession(
            id="new-checkout",
            user_id=old.user_id,
            environment="test",
            idempotency_key="new-checkout-key",
            status="pending",
            product_id=old.product_id,
            plan_version=old.plan_version,
            amount_minor=990,
            currency="USD",
            limit_seconds=1800,
            max_clip_seconds=90,
            success_url=old.success_url,
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
        session.add(new)
        session.commit()
        state = billing_state(session, old.user_id)
        assert state["checkout_status"] == "pending"
        assert state["sync_state"] == "payment_confirming"


@pytest.mark.parametrize(
    "address",
    ["x@example.com\r\nBcc:someone@example.com", "not-email", "a@b", "a@b.com?subject=bad"],
)
def test_support_contact_rejects_injected_mailto_contract(address):
    from app.settings import Settings

    with pytest.raises(ValueError):
        Settings(_env_file=None, support_email=address)
