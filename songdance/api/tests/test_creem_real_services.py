"""Opt-in billing races against disposable PostgreSQL; provider calls stay offline."""

import hashlib
import hmac
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import BillingWebhookEvent, CheckoutSession, PaidPeriod, UsagePeriod, User
from app.services.billing import create_checkout
from app.services.billing_events import process_pending, receive_event, sync_checkout
from tests.test_auth_ownership import auth_settings
from tests.test_auth_real_services import postgres  # noqa: F401
from tests.test_creem_billing import SECRET, FakeProvider

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)
API_ROOT = Path(__file__).resolve().parents[1]


def migrate(url, *args, check=True):
    return subprocess.run(
        [str(API_ROOT / ".venv/bin/alembic"), *args],
        cwd=API_ROOT,
        env={**os.environ, "SONGDANCE_DATABASE_URL": url, "SONGDANCE_AUTH_ENABLED": "false"},
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture
def database(postgres):  # noqa: F811
    admin, _ = postgres
    name = "creem_test_" + uuid4().hex
    with psycopg.connect(admin, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = admin.rsplit("/", 1)[0] + "/" + name
    engine = create_engine(url.replace("postgresql://", "postgresql+psycopg://"))
    try:
        migrate(url, "upgrade", "009")
        yield url, engine, sessionmaker(engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with psycopg.connect(admin, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name))
            )


def owner(factory):
    user_id = str(uuid4())
    with factory.begin() as session:
        session.add(User(id=user_id, active=True))
    return user_id


def signed_event(factory, event_id="evt_paid", kind="subscription.paid", obj=None):
    raw = json.dumps(
        {
            "id": event_id,
            "eventType": kind,
            "object": obj
            or {
                "id": "sub_test",
                "mode": "test",
                "last_transaction_id": "tx_test",
            },
        }
    ).encode()
    signature = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    with factory.begin() as session:
        return receive_event(session, raw, signature, SECRET)


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_checkout_posts_once_and_reuses_durable_open_intent(
    database, tmp_path, same_key
):
    _, _, factory = database
    user_id = owner(factory)
    settings = auth_settings(tmp_path).model_copy(update={"creem_product_id": "prod_test"})
    provider = FakeProvider()
    entered, release = Event(), Event()
    original = provider.create_checkout

    def held_post(**kwargs):
        entered.set()
        assert release.wait(10), "checkout test did not release offline provider"
        return original(**kwargs)

    provider.create_checkout = held_post

    def checkout(key):
        with factory() as session:
            result = create_checkout(session, session.get(User, user_id), key, settings, provider)
            session.commit()
            return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(checkout, "key_one")
        try:
            assert entered.wait(10)
            second = pool.submit(checkout, "key_one" if same_key else "key_two").result(timeout=10)
            assert second["status"] == "creating"
        finally:
            release.set()
        completed = first.result(timeout=10)
    assert second["id"] == completed["id"]
    assert completed["status"] == "pending"
    assert len(provider.create_calls) == 1
    with factory() as session:
        assert len(session.scalars(select(CheckoutSession)).all()) == 1


def test_simultaneous_duplicate_webhooks_have_one_inbox_row(database):
    _, engine, factory = database
    barrier = Barrier(2)

    def synchronize_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT") and "billing_webhook_events.event_id =" in statement:
            if not conn.info.get("initial_inbox_read"):
                conn.info["initial_inbox_read"] = True
                barrier.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_reads)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: signed_event(factory), range(2)))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_reads)
    assert results[0] == results[1]
    with factory() as session:
        assert len(session.scalars(select(BillingWebhookEvent)).all()) == 1


def test_competing_workers_grant_payment_once(database, tmp_path):
    _, engine, factory = database
    user_id = owner(factory)
    provider = FakeProvider()
    settings = auth_settings(tmp_path).model_copy(update={"creem_product_id": "prod_test"})
    with factory() as session:
        create_checkout(session, session.get(User, user_id), "key_one", settings, provider)
    provider.checkout["status"] = "completed"
    with factory.begin() as session:
        sync_checkout(session, provider, "ch_test")
    signed_event(factory)
    barrier = Barrier(2)

    def synchronize_candidates(conn, cursor, statement, parameters, context, executemany):
        if (
            statement.startswith("SELECT billing_webhook_events.id ")
            and "FOR UPDATE" not in statement
        ):
            barrier.wait(timeout=10)

    event.listen(engine, "after_cursor_execute", synchronize_candidates)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            counts = list(pool.map(lambda _: process_pending(factory, provider), range(2)))
    finally:
        event.remove(engine, "after_cursor_execute", synchronize_candidates)
    assert sum(counts) == 1
    with factory() as session:
        periods = session.scalars(select(PaidPeriod)).all()
        assert len(periods) == 1 and periods[0].status == "active"
        usage = session.get(UsagePeriod, periods[0].usage_period_id)
        assert (usage.limit_units, usage.reserved_units, usage.consumed_units) == (1800, 0, 0)
        inbox = session.scalar(select(BillingWebhookEvent))
        assert (inbox.status, inbox.attempts) == ("processed", 1)


def test_009_partial_unique_index_and_history_guard(database):
    url, _, factory = database
    user_id = owner(factory)

    def intent(status):
        return CheckoutSession(
            id=uuid4().hex,
            user_id=user_id,
            environment="test",
            idempotency_key=uuid4().hex,
            status=status,
            product_id="prod_test",
            plan_version="test",
            amount_minor=990,
            currency="USD",
            limit_seconds=1800,
            max_clip_seconds=90,
            success_url="http://localhost:3000/billing/return",
        )

    with factory.begin() as session:
        session.add_all([intent("completed"), intent("expired"), intent("creating")])
    for status in ("creating", "pending", "uncertain"):
        with pytest.raises(IntegrityError) as error, factory.begin() as session:
            session.add(intent(status))
        assert error.value.orig.diag.constraint_name == "uq_checkout_open"
    result = migrate(url, "downgrade", "008", check=False)
    assert result.returncode != 0
    assert "Cannot remove billing identity or audit history" in result.stderr
    with factory() as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "009"
        assert len(session.scalars(select(CheckoutSession)).all()) == 3


def test_empty_009_migration_round_trip(database):
    url, engine, _ = database
    migrate(url, "downgrade", "008")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT to_regclass('checkout_sessions')")) is None
    migrate(url, "upgrade", "009")
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "009"
        assert connection.scalar(text("SELECT count(*) FROM billing_webhook_events")) == 0
