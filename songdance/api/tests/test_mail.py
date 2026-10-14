import asyncio
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError
from standardwebhooks import Webhook

from app.main import create_app
from app.models import MailDelivery, MailEvent, MailSuppression
from app.services.mail_contract import MailError, event_key, message_bytes, otp_message
from app.services.mail_delivery import MailDeliveryService
from app.services.resend_client import ResendClient
from app.settings import Settings
from tests.conftest import RecordingQueue

HOOK_SECRET = "whsec_" + base64.b64encode(b"h" * 32).decode()
EVENT_SECRET = "whsec_" + base64.b64encode(b"e" * 32).decode()
PROVIDER_ID = "56761188-7520-42d8-8898-ff6fc54ce618"


def config(tmp_path, **overrides):
    return Settings(_env_file=None, **{
        "environment": "test", "database_url": f"sqlite:///{tmp_path / 'mail.sqlite3'}",
        "auto_create_schema": True, "quota_backend": "memory",
        "local_storage_path": tmp_path / "storage", "temp_path": tmp_path / "tmp",
        "mail_enabled": True, "mail_project_ref": "abcdefghijklmnopqrst",
        "supabase_url": "https://abcdefghijklmnopqrst.supabase.co",
        "cors_origins": "http://127.0.0.1:3002", "mail_site_url": "http://127.0.0.1:3002",
        "mail_test_recipients": "test@example.invalid", "support_email": "help@example.invalid",
        "mail_support_verified": True, "resend_api_key": "re_synthetic_test_key",
        "supabase_email_hook_secret": "v1," + HOOK_SECRET,
        "resend_webhook_secret": EVENT_SECRET, "mail_digest_secret": "d" * 32,
        **overrides,
    })


class Provider:
    def __init__(self):
        self.calls = []
        self.status = 200
        self.body = {"id": PROVIDER_ID}
        self.headers = {}
        self.fail = False

    def handle(self, request):
        self.calls.append(request)
        if self.fail:
            raise httpx.ReadTimeout("private upstream body and token must not leak")
        return httpx.Response(self.status, json=self.body, headers=self.headers)


@pytest.fixture
def mail(tmp_path):
    app = create_app(config(tmp_path), job_queue=RecordingQueue())
    provider = Provider()
    app.state.mail_client = ResendClient("re_synthetic_test_key", transport=httpx.MockTransport(
        provider.handle,
    ))
    with TestClient(app) as client:
        yield client, provider, app.state.session_factory
    app.state.engine.dispose()


def payload(**overrides):
    return {
        "user": {"id": "00000000-0000-0000-0000-000000000001", "email": "test@example.invalid"},
        "email_data": {"site_url": "https://abcdefghijklmnopqrst.supabase.co/auth/v1",
                       "token": "18493726",
                       "token_hash": "private-hash", "redirect_to": "https://evil.invalid/",
                       "email_action_type": "magiclink", **overrides},
    }


def post(client, data, *, event_id="evt_test", resend=False, age=0, raw=None, headers=None):
    raw = raw if raw is not None else json.dumps(data).encode()
    when = datetime.now(UTC) + timedelta(seconds=age)
    prefix, secret = ("svix", EVENT_SECRET) if resend else ("webhook", HOOK_SECRET)
    signed = {
        f"{prefix}-id": event_id, f"{prefix}-timestamp": str(int(when.timestamp())),
        f"{prefix}-signature": Webhook(secret).sign(event_id, when, raw.decode()),
        "Content-Type": "application/json", "Origin": "https://untrusted.invalid",
        **(headers or {}),
    }
    return client.post("/webhooks/resend" if resend else "/webhooks/supabase/email",
                       content=raw, headers=signed)


def due(sessions, **values):
    with sessions() as session:
        row = session.scalar(select(MailDelivery))
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        for key, value in values.items():
            setattr(row, key, value)
        session.commit()


@pytest.mark.parametrize("action", ["signup", "magiclink", "reauthentication"])
@pytest.mark.parametrize("token", ["184937", "18493726"])
def test_send_safe_template_and_durable_duplicate(mail, action, token):
    client, provider, sessions = mail
    data = payload(email_action_type=action, token=token)
    assert post(client, data).status_code == 200
    assert post(client, data).status_code == 200
    assert len(provider.calls) == 1
    request = provider.calls[0]
    body = json.loads(request.content)
    assert body["from"] == "auth@mail.notavue.io"
    assert body["reply_to"] == "help@example.invalid"
    assert token in body["html"] and token in body["text"]
    assert token not in body["subject"]
    assert "evil.invalid" not in str(body) and "private-hash" not in str(body)
    assert "/privacy" in body["html"] and "/refund" in body["html"]
    assert request.headers["Idempotency-Key"].startswith("songdance-otp/")
    with sessions() as session:
        row = session.scalar(select(MailDelivery))
        assert row.status == "accepted" and row.attempts == 1 and row.provider_id == PROVIDER_ID
        stored = str(session.execute(text("SELECT * FROM mail_deliveries")).all())
        for private in (token, "test@example.invalid", "private-hash", HOOK_SECRET):
            assert private not in stored


@pytest.mark.parametrize("age", [-301, 301])
def test_expired_or_future_signature(mail, age):
    client, provider, _ = mail
    assert post(client, payload(), age=age).status_code == 401
    assert not provider.calls


@pytest.mark.parametrize("signature", ["", "bad", "v1,%%%", "v2,AAAA", "v1,a,b"])
def test_malformed_signature_safe_failure(mail, signature):
    client, provider, _ = mail
    result = post(client, payload(), headers={"webhook-signature": signature})
    assert result.status_code == 401 and "private-hash" not in result.text
    assert not provider.calls


def test_raw_body_mismatch_and_wrong_provider_headers(mail):
    client, provider, _ = mail
    when = datetime.now(UTC)
    raw = json.dumps(payload())
    signature = Webhook(HOOK_SECRET).sign("id", when, raw)
    assert post(client, payload(), event_id="id", raw=(raw + " ").encode(),
                headers={"webhook-signature": signature}).status_code == 401
    assert client.post("/webhooks/supabase/email", json=payload(), headers={
        "svix-id": "id", "svix-timestamp": str(int(when.timestamp())),
        "svix-signature": signature,
    }).status_code == 401
    assert not provider.calls


@pytest.mark.parametrize("fields", [
    {"token": "1234567"}, {"token": "１２３４５６７８"}, {"token": "<script>"},
    {"email_action_type": "email_change"}, {"email_action_type": "recovery"},
    {"email_action_type": "invite"}, {"site_url": "https://evil.invalid"},
    {"email_action_type": []},
])
def test_contract_rejects_invalid_otp_or_unsupported_flow(mail, fields):
    client, provider, _ = mail
    assert post(client, payload(**fields)).status_code == 400
    assert not provider.calls


def test_failure_diagnostics_contain_only_fixed_fields(mail, monkeypatch):
    client, provider, _ = mail
    logs = []
    monkeypatch.setattr("app.routes.mail.log_event", lambda name, **fields: logs.append(
        (name, fields),
    ))
    assert post(client, payload(site_url="https://private.invalid")).status_code == 400
    assert logs == [("mail_hook_rejected", {"provider": "supabase",
                    "error_code": "MAIL_PROVIDER_URL_MISMATCH", "status_code": 400})]
    assert not provider.calls


@pytest.mark.parametrize("site", ["https://abcdefghijklmnopqrst.supabase.co",
                                  "https://abcdefghijklmnopqrst.supabase.co/auth/v1"])
def test_provider_url_is_distinct_from_server_owned_template_links(mail, site):
    client, provider, _ = mail
    assert post(client, payload(site_url=site)).status_code == 200
    message = json.loads(provider.calls[0].content)
    assert "http://127.0.0.1:3002/privacy" in message["text"]
    assert "http://127.0.0.1:3002/refund" in message["html"]
    assert ".supabase.co" not in message["text"] + message["html"]


@pytest.mark.parametrize("site", [None, [], "http://127.0.0.1:3002",
    "https://otherproject.supabase.co/auth/v1",
    "https://abcdefghijklmnopqrst.supabase.co.evil.invalid/auth/v1",
    "https://abcdefghijklmnopqrst.supabase.co@evil.invalid/auth/v1",
    "https://abcdefghijklmnopqrst.supabase.co/auth/v1?redirect_to=https://evil.invalid",
    "https://abcdefghijklmnopqrst.supabase.co/auth/v1/verify",
])
def test_hook_rejects_unbound_provider_urls(mail, site):
    client, provider, _ = mail
    result = post(client, payload(site_url=site))
    assert result.status_code == 400
    assert result.json()["error"]["message"] == "MAIL_PROVIDER_URL_MISMATCH"
    assert not provider.calls


def test_recipient_allowlist_disabled_and_size_gates(mail):
    client, provider, _ = mail
    data = payload()
    data["user"]["email"] = "other@example.invalid"
    assert post(client, data).status_code == 400
    assert post(client, {}, raw=b" " * 20481).status_code == 413
    client.app.state.settings.mail_enabled = False
    assert post(client, payload()).status_code == 503
    assert post(client, {}, resend=True).status_code == 503
    assert not provider.calls


def test_same_id_different_payload_or_template_configuration_conflicts(mail):
    client, provider, _ = mail
    assert post(client, payload()).status_code == 200
    assert post(client, payload(token="87654321")).status_code == 409
    client.app.state.settings.support_email = "other@example.invalid"
    assert post(client, payload()).status_code == 409
    assert len(provider.calls) == 1


def test_timeout_retries_same_body_and_key_without_claiming_success(mail, caplog):
    client, provider, sessions = mail
    provider.fail = True
    result = post(client, payload())
    assert result.status_code == 503 and result.headers["Retry-After"] == "2"
    with sessions() as session:
        assert session.scalar(select(MailDelivery)).status == "unknown"
    assert "18493726" not in caplog.text and "private upstream" not in caplog.text
    assert post(client, payload()).status_code == 503
    assert len(provider.calls) == 1
    due(sessions)
    provider.fail = False
    assert post(client, payload()).status_code == 200
    assert provider.calls[0].content == provider.calls[1].content
    assert (
        provider.calls[0].headers["Idempotency-Key"] == provider.calls[1].headers["Idempotency-Key"]
    )


@pytest.mark.parametrize("status,name,retry", [
    (429, "rate_limit_exceeded", True), (503, "service_unavailable", True),
    (409, "concurrent_idempotent_requests", True),
    (429, "daily_quota_exceeded", False), (429, "monthly_quota_exceeded", False),
    (409, "invalid_idempotent_request", False), (401, "missing_api_key", False),
    (403, "validation_error", False), (422, "validation_error", False),
    (307, "redirect", False),
])
def test_provider_error_classification_and_bounded_retries(mail, status, name, retry):
    client, provider, sessions = mail
    provider.status, provider.body = status, {"name": name, "message": "SECRET"}
    response = post(client, payload())
    assert response.status_code == (503 if retry else 400)
    assert "SECRET" not in response.text
    due(sessions)
    post(client, payload())
    due(sessions)
    post(client, payload())
    due(sessions)
    assert post(client, payload()).status_code == 400
    assert len(provider.calls) == (3 if retry else 1)


def test_expiry_and_provider_retry_after_are_enforced(mail):
    client, provider, sessions = mail
    provider.status, provider.body, provider.headers = 429, {}, {"retry-after": "30"}
    result = post(client, payload())
    assert result.headers["retry-after"] == "30"
    assert post(client, payload()).status_code == 503
    due(sessions, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    assert post(client, payload()).status_code == 400
    assert len(provider.calls) == 1


def test_restart_recovers_sending_lease_and_provider_accept_before_db_failure(mail, monkeypatch):
    client, provider, sessions = mail
    original = MailDeliveryService.finish
    def fail(*args):
        raise OperationalError("safe", None, None)
    monkeypatch.setattr(MailDeliveryService, "finish", fail)
    assert post(client, payload()).status_code == 503
    due(sessions)
    monkeypatch.setattr(MailDeliveryService, "finish", original)
    assert post(client, payload()).status_code == 200
    assert (
        provider.calls[0].headers["Idempotency-Key"] == provider.calls[1].headers["Idempotency-Key"]
    )


def test_concurrent_claim_has_one_winner_and_fences_old_attempt(mail):
    client, _, sessions = mail
    settings = client.app.state.settings
    service = MailDeliveryService(settings, sessions)
    data = payload()
    key = event_key(settings, "supabase", "race")
    body, action = otp_message(settings, data, key)
    def claim():
        try:
            return service.claim(key, json.dumps(data).encode(), message_bytes(body),
                                 body["to"][0], action)
        except MailError:
            return -1
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: claim(), range(4)))
    assert results.count(1) == 1
    due(sessions)
    assert claim() == 2
    from app.services.resend_client import SendResult
    with pytest.raises(MailError, match="SUPERSEDED"):
        service.finish(key, 1, SendResult("accepted", PROVIDER_ID))


def event(client, kind="email.bounced", **overrides):
    settings = client.app.state.settings
    return {"type": kind, "data": {
        "email_id": PROVIDER_ID, "from": settings.mail_from, "to": ["test@example.invalid"],
        "tags": {"songdance_delivery": event_key(settings, "supabase", "evt_test")},
        "bounce": {"type": "Permanent", "message": "PRIVATE SMTP DIAGNOSTIC"}, **overrides,
    }}


@pytest.mark.parametrize("kind", ["email.bounced", "email.complained", "email.suppressed"])
def test_signed_callbacks_idempotent_and_late_delivery_cannot_unsuppress(mail, kind):
    client, provider, sessions = mail
    assert post(client, payload()).status_code == 200
    data = event(client, kind)
    assert post(client, data, resend=True).status_code == 200
    assert post(client, data, resend=True).status_code == 200
    assert post(client, event(client, "email.delivered"), resend=True,
                event_id="evt_delivered").status_code == 200
    assert post(client, payload(), event_id="new_otp").status_code == 400
    assert len(provider.calls) == 1
    with sessions() as session:
        assert len(session.scalars(select(MailSuppression)).all()) == 1
        assert len(session.scalars(select(MailEvent)).all()) == 2
        stored = str(session.execute(text("SELECT * FROM mail_events")).all())
        assert "PRIVATE" not in stored and "test@example.invalid" not in stored
    # A replay of the same event ID with altered body must not get a success response.
    assert post(client, event(client, "email.delivered"), resend=True).status_code == 409


def test_unrelated_event_and_temporary_bounce_do_not_suppress(mail):
    client, _, sessions = mail
    assert post(client, payload()).status_code == 200
    for data in [event(client, tags={}), event(client, bounce={"type": "Temporary"})]:
        assert post(client, data, resend=True, event_id=str(uuid4())).status_code == 200
    with sessions() as session:
        assert session.scalar(select(MailSuppression)) is None


def test_event_before_send_result_is_durable_and_forged_or_mismatched_events_rejected(mail):
    client, provider, sessions = mail
    provider.fail = True
    assert post(client, payload()).status_code == 503
    assert post(client, event(client), resend=True,
                headers={"svix-signature": "v1,bad"}).status_code == 401
    assert post(client, event(client, to=["other@example.invalid"]), resend=True).status_code == 400
    assert post(client, event(client), resend=True).status_code == 200
    due(sessions)
    assert post(client, payload()).status_code == 400


def test_concurrent_callbacks_commit_one_event_and_suppression(mail):
    client, _, sessions = mail
    assert post(client, payload()).status_code == 200
    service = MailDeliveryService(client.app.state.settings, sessions)
    data = event(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.receive_event("race", json.dumps(data).encode(), data),
                      range(4)))
    with sessions() as session:
        assert len(session.scalars(select(MailEvent)).all()) == 1
        assert len(session.scalars(select(MailSuppression)).all()) == 1


@pytest.mark.parametrize("change", [
    {"environment": "production"}, {"mail_support_verified": False},
    {"mail_test_recipients": ""}, {"mail_from": "attacker@other.invalid"},
    {"supabase_url": "https://other.supabase.co"}, {"mail_site_url": "https://evil.invalid"},
    {"mail_digest_secret": "short"}, {"supabase_email_hook_secret": "invalid"},
    {"resend_webhook_secret": HOOK_SECRET},
])
def test_config_fails_closed_without_logging_secrets(tmp_path, change):
    with pytest.raises(ValueError) as error:
        config(tmp_path, **change)
    assert HOOK_SECRET not in str(error.value)


def test_transport_total_deadline_is_bounded(monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.1)
                yield b" "
    async def slow(request):
        return httpx.Response(200, stream=SlowStream())
    async def run():
        start = asyncio.get_running_loop().time()
        result = await ResendClient("fake", transport=httpx.MockTransport(slow)).send(b"{}", "k")
        assert asyncio.get_running_loop().time() - start < 3.7
        assert result.status == "unknown"
    asyncio.run(run())


@pytest.mark.parametrize("response", [{"id": "bad"}, {"id": None}, [], {"large": "a" * 40000}])
def test_invalid_provider_success_is_unknown(mail, response):
    client, provider, sessions = mail
    provider.body = response
    assert post(client, payload()).status_code == 503
    with sessions() as session:
        assert session.scalar(select(MailDelivery)).status == "unknown"


def test_provider_malformed_error_fields_do_not_crash(mail):
    client, provider, _ = mail
    provider.status, provider.body = 429, {"name": ["invalid"]}
    provider.headers = {"retry-after": "9" * 5000}
    result = post(client, payload())
    assert result.status_code == 503 and result.headers["Retry-After"] == "60"


def test_duplicate_signature_header_rejected(mail):
    client, provider, _ = mail
    response = client.post("/webhooks/supabase/email", content=b"{}", headers=[
        ("webhook-id", "first"), ("webhook-id", "second"),
        ("webhook-timestamp", "0"), ("webhook-signature", "v1,anything"),
    ])
    assert response.status_code == 401
    assert not provider.calls


def test_database_unavailable_never_sends_or_acknowledges_callback(mail, monkeypatch):
    client, provider, _ = mail
    def broken():
        raise OperationalError("private-db-connection", None, None)
    monkeypatch.setattr(client.app.state, "session_factory", broken)
    for data, resend in [(payload(), False), (event(client), True)]:
        response = post(client, data, resend=resend)
        assert response.status_code == 503
        assert "private-db-connection" not in response.text
    assert not provider.calls


def test_new_mail_origin_exception_does_not_allow_other_write_routes(mail):
    client, _, _ = mail
    response = client.post("/jobs", json={}, headers={"Origin": "https://untrusted.invalid"})
    assert response.status_code == 403


def test_whole_hook_deadline_without_fake_success(mail):
    client, _, sessions = mail
    class SlowSender:
        async def send(self, body, key):
            await asyncio.sleep(6)
            pytest.fail("Cancelled send should never finish")
    client.app.state.mail_client = SlowSender()
    import time
    start = time.monotonic()
    result = post(client, payload())
    assert result.status_code == 503 and time.monotonic() - start < 4.8
    with sessions() as session:
        assert session.scalar(select(MailDelivery)).status == "sending"


def test_malformed_bounce_is_not_silently_acknowledged(mail):
    client, _, _ = mail
    assert post(client, payload()).status_code == 200
    assert post(client, event(client, bounce={"type": []}), resend=True).status_code == 400


def test_official_svix_vector_via_standard_webhooks_adapter(monkeypatch):
    from standardwebhooks import webhooks

    from app.services.mail_contract import verified_payload
    class FixedTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(1614265330, UTC)
    monkeypatch.setattr(webhooks, "datetime", FixedTime)
    # Public, non-secret vector from docs.svix.com/receiving/verifying-payloads/how.
    event_id, data = verified_payload(b'{"test": 2432232314}', {
        "svix-id": "msg_p5jXN8AQM9LWM0D4loKWxJek", "svix-timestamp": "1614265330",
        "svix-signature": "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE=",
    }, "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw", resend=True)
    assert event_id == "msg_p5jXN8AQM9LWM0D4loKWxJek" and data == {"test": 2432232314}


def test_same_signing_secret_with_different_base64_padding_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="independent"):
        config(tmp_path, resend_webhook_secret=HOOK_SECRET.rstrip("="))
