"""The temporary billing listener exposes only the existing signed inbox handler."""

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.billing_hook import create_billing_hook_app
from app.models import BillingWebhookEvent, PaidPeriod
from app.settings import Settings
from scripts.run_billing_hook import load_settings
from tests.test_auth_ownership import auth_settings
from tests.test_creem_billing import SECRET, event
from tests.test_migrations import run_alembic


def settings_for(tmp_path, **overrides):
    values = auth_settings(tmp_path).model_dump()
    values.update(
        environment="test", billing_environment="test", auto_create_schema=False,
        usage_enabled=True, paid_usage_enabled=True, creem_enabled=True,
        creem_product_id="prod_test", creem_api_key=SecretStr("creem_test_offline"),
        creem_webhook_secret=SecretStr(SECRET),
        creem_success_url="http://localhost:3000/billing/return",
    )
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def client(tmp_path):
    settings = settings_for(tmp_path)
    run_alembic(settings.database_url, "head")
    with TestClient(create_billing_hook_app(settings)) as client:
        yield client


def test_exact_route_and_invalid_signatures_do_not_persist(client):
    for path in ("/", "/docs", "/redoc", "/openapi.json", "/health", "/me", "/jobs",
                 "/billing/config", "/billing/checkout", "/billing/portal",
                 "/webhooks/creem/", "/webhooks/resend"):
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404
    assert client.get("/webhooks/creem").status_code == 405
    assert client.post("/webhooks/creem", json={}).status_code == 400
    assert client.post("/webhooks/creem", content=b"{}",
                       headers={"creem-signature": "0" * 64}).status_code == 400
    assert client.post("/webhooks/creem", content=b"x" * (256 * 1024 + 1),
                       headers={"creem-signature": "0" * 64}).status_code == 413
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(BillingWebhookEvent)) == 0


def test_signed_inbox_is_durable_idempotent_and_does_not_grant_access(client):
    assert event(client, "subscription.paid", "evt_listener").status_code == 200
    assert event(client, "subscription.paid", "evt_listener").status_code == 200
    assert event(client, "subscription.canceled", "evt_listener").status_code == 400
    assert event(client, "subscription.paid", "evt_live",
                 {"id": "sub_test", "mode": "prod"}).status_code == 400
    with client.app.state.session_factory() as session:
        rows = list(session.scalars(select(BillingWebhookEvent)))
        assert len(rows) == 1 and rows[0].status == "pending"
        assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 0


def test_migrations_and_enabled_setting_fail_closed(tmp_path):
    settings = settings_for(tmp_path, creem_enabled=False)
    with pytest.raises(ValueError, match="migration"):
        with TestClient(create_billing_hook_app(settings)):
            pytest.fail("Listener must require migrated inbox")
    run_alembic(settings.database_url, "head")
    with TestClient(create_billing_hook_app(settings)) as client:
        assert event(client, "subscription.paid", "evt_disabled").status_code == 503
    for overrides in ({"environment": "development"}, {"auto_create_schema": True},
                      {"billing_environment": "live"}):
        with pytest.raises(ValueError, match="test mode"):
            create_billing_hook_app(settings.model_copy(update=overrides))


def test_explicit_private_file_ignores_process_settings(tmp_path, monkeypatch):
    path = tmp_path / "billing.env"
    content = (
        "SONGDANCE_ENVIRONMENT=test\nSONGDANCE_BILLING_ENVIRONMENT=test\n"
        "SONGDANCE_AUTO_CREATE_SCHEMA=false\nSONGDANCE_CREEM_ENABLED=false\n"
        f"SONGDANCE_DATABASE_URL=sqlite:///{tmp_path / 'billing.sqlite3'}\n"
        "NEXT_PUBLIC_SITE_URL=http://127.0.0.1:3002\n"
    )
    path.write_text(content)
    path.chmod(0o600)
    monkeypatch.setenv("SONGDANCE_CREEM_ENABLED", "true")
    monkeypatch.setenv("SONGDANCE_ENVIRONMENT", "production")
    monkeypatch.setenv("SONGDANCE_CREEM_API_KEY", "private_sentinel")
    settings = load_settings(path)
    assert settings.environment == "test" and not settings.creem_enabled
    assert not settings.creem_api_key.get_secret_value()
    path.chmod(0o644)
    with pytest.raises(ValueError, match="PRIVATE_ENV"):
        load_settings(path)
    path.chmod(0o600)
    path.write_text(content + "UNSUPPORTED_KEY=private_sentinel\n")
    with pytest.raises(ValueError, match="UNSUPPORTED"):
        load_settings(path)
