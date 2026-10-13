"""Opt-in isolated PostgreSQL only. Provider calls remain mocked; no real mail."""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.database import create_db_engine, create_session_factory
from app.models import MailDelivery, MailEvent, MailSuppression
from app.services.mail_contract import MailError, event_key, message_bytes, otp_message
from app.services.mail_delivery import MailDeliveryService
from app.services.resend_client import SendResult
from tests.test_auth_real_services import postgres  # noqa: F401
from tests.test_mail import PROVIDER_ID, config, payload
from tests.test_migrations import run_alembic

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_MAIL_SERVICES") != "1",
    reason="Opt in to a temporary PostgreSQL cluster; no existing services or real emails",
)


def test_postgres_migration_claim_and_event_races(postgres, tmp_path):  # noqa: F811
    admin, _ = postgres
    settings = config(tmp_path, database_url=admin, auto_create_schema=False)
    run_alembic(settings.database_url, "head")
    engine = create_db_engine(settings)
    sessions = create_session_factory(engine)
    service = MailDeliveryService(settings, sessions)
    key = event_key(settings, "supabase", "race")
    data = payload()
    message, action = otp_message(settings, data, key)
    raw, encoded = json.dumps(data).encode(), message_bytes(message)
    def claim():
        try:
            return service.claim(key, raw, encoded, message["to"][0], action)
        except MailError:
            return -1
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: claim(), range(8)))
        assert results.count(1) == 1
        service.finish(key, 1, SendResult("accepted", PROVIDER_ID))
        event = {"type": "email.complained", "data": {
            "email_id": PROVIDER_ID, "from": settings.mail_from, "to": message["to"],
            "tags": {"songdance_delivery": key},
        }}
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(
                lambda _: service.receive_event("race", json.dumps(event).encode(), event),
                range(8),
            ))
        with sessions() as session:
            assert session.scalar(select(MailDelivery)).attempts == 1
            assert len(session.scalars(select(MailEvent)).all()) == 1
            assert len(session.scalars(select(MailSuppression)).all()) == 1
        with pytest.raises(MailError, match="SUPPRESSED"):
            service.claim("new-otp", raw, encoded, message["to"][0], action)
    finally:
        engine.dispose()
