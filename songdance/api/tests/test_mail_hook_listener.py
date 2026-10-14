"""The temporary public listener must expose only signed mail callbacks."""

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.mail_hook import create_mail_hook_app
from app.services.resend_client import ResendClient
from scripts.run_mail_hook import load_settings, preflight
from tests.test_mail import Provider, config, event, payload, post
from tests.test_migrations import run_alembic


@dataclass
class Listener:
    client: TestClient
    provider: Provider


@pytest.fixture
def listener(tmp_path):
    settings = config(tmp_path, auto_create_schema=False)
    run_alembic(settings.database_url, "head")
    app = create_mail_hook_app(settings)
    provider = Provider()
    app.state.mail_client = ResendClient("re_synthetic_test_key", transport=httpx.MockTransport(
        provider.handle,
    ))
    with TestClient(app) as client:
        yield Listener(client, provider)


def test_only_two_exact_post_routes_are_public(listener):
    client = listener.client
    for path in ("/", "/docs", "/redoc", "/openapi.json", "/health", "/me", "/auth/otp",
                 "/jobs", "/webhooks/creem", "/webhooks/resend/", "/webhooks/supabase/email/"):
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404
    for path in ("/webhooks/supabase/email", "/webhooks/resend"):
        assert client.get(path).status_code == 405
        assert client.post(path, json={}).status_code == 401
    assert not listener.provider.calls


def test_real_handler_signatures_deduplication_and_suppression(listener):
    client, provider = listener.client, listener.provider
    assert post(client, payload()).status_code == 200
    assert post(client, payload()).status_code == 200
    assert len(provider.calls) == 1
    assert post(client, event(client), resend=True).status_code == 200
    assert post(client, payload(), event_id="another_otp").status_code == 400
    assert len(provider.calls) == 1


def test_missing_migration_and_disabled_listener_fail_closed(tmp_path):
    settings = config(tmp_path, mail_enabled=False, auto_create_schema=False)
    app = create_mail_hook_app(settings)
    with pytest.raises(ValueError, match="migration 014"):
        with TestClient(app):
            pytest.fail("Must not accept requests before schema is ready")
    run_alembic(settings.database_url, "head")
    with TestClient(app) as client:
        assert post(client, payload()).status_code == 503
        assert post(client, event(client), resend=True).status_code == 503


def test_test_mode_and_manual_schema_are_required(tmp_path):
    with pytest.raises(ValueError, match="test mode"):
        create_mail_hook_app(config(tmp_path, auto_create_schema=True))
    with pytest.raises(ValueError, match="test mode"):
        create_mail_hook_app(config(tmp_path, environment="development", auto_create_schema=False))


def private_file(tmp_path: Path) -> Path:
    path = tmp_path / "listener.env"
    path.write_text(
        "SONGDANCE_ENVIRONMENT=test\nSONGDANCE_AUTO_CREATE_SCHEMA=false\n"
        f"SONGDANCE_DATABASE_URL=sqlite:///{tmp_path / 'listener.sqlite3'}\n"
        "SONGDANCE_MAIL_ENABLED=false\n"
    )
    path.chmod(0o600)
    return path


def test_explicit_file_ignores_process_configuration(tmp_path, monkeypatch):
    path = private_file(tmp_path)
    monkeypatch.setenv("SONGDANCE_MAIL_ENABLED", "true")
    monkeypatch.setenv("SONGDANCE_ENVIRONMENT", "production")
    monkeypatch.setenv("SONGDANCE_RESEND_API_KEY", "re_PRIVATE_SENTINEL")
    settings = load_settings(path)
    assert settings.environment == "test" and not settings.mail_enabled
    assert not settings.resend_api_key.get_secret_value()
    report, _ = preflight(path)
    assert not report["mail_configuration_ready"]
    assert "SONGDANCE_RESEND_API_KEY" in report["missing_fields"]
    assert "PRIVATE_SENTINEL" not in str(report)


def test_private_file_and_safe_diagnostics(tmp_path):
    path = private_file(tmp_path)
    path.chmod(0o644)
    assert preflight(path)[1] is None
    path.chmod(0o600)
    for extra in ("UNSUPPORTED_SECRET=PRIVATE_SENTINEL\n",
                  "SONGDANCE_MAIL_ENABLED=true\n",
                  "SONGDANCE_RESEND_API_KEY=re_PRIVATE_SENTINEL\nSONGDANCE_HOURLY_JOB_LIMIT=bad\n"):
        original = path.read_text()
        path.write_text(original + extra)
        report, settings = preflight(path)
        assert settings is None and not report["configuration_format_valid"]
        assert "PRIVATE_SENTINEL" not in str(report)
        path.write_text(original)
