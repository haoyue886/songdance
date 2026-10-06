import subprocess
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models import Base, User
from app.models.billing import (
    BillingAccount,
    BillingSubscription,
    BillingWebhookEvent,
    CheckoutSession,
)
from tests.test_migrations import run_alembic

TABLES = {
    "billing_accounts", "checkout_sessions", "billing_subscriptions", "billing_webhook_events"
}


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'creem.sqlite3'}"
    run_alembic(url, "009", direction="upgrade")
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def test_009_schema_matches_models_and_empty_downgrade(migrated):
    url, engine = migrated
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, compare_to:
                name in TABLES if kind == "table" else True,
            "compare_server_default": True,
        })
        assert compare_metadata(context, Base.metadata) == []
    run_alembic(url, "008")
    assert not TABLES.intersection(inspect(engine).get_table_names())


def test_009_upgrade_preserves_free_and_paid_history(tmp_path):
    from tests.test_entitlements import grant

    url = f"sqlite:///{tmp_path / 'old-history.sqlite3'}"
    run_alembic(url, "008", direction="upgrade")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            session.add(User(id="owner"))
            session.commit()
            grant(session, "owner")
            session.commit()
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO usage_periods (id,user_id,entitlement_type,period_key,"
                "period_start,period_end,limit_units,reserved_units,consumed_units) "
                "VALUES ('free','owner','free_month','free:2026-10',"
                "'2026-10-01','2026-11-01',600,0,12)"
            ))
            connection.execute(text(
                "INSERT INTO usage_ledger "
                "(id,period_id,user_id,reservation_id,event_type,units) "
                "VALUES ('ledger','free','owner','reservation','consume',12)"
            ))
            snapshots = {
                table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
                for table in ("users", "usage_periods", "usage_ledger", "paid_periods")
            }
        run_alembic(url, "009", direction="upgrade")
        with engine.connect() as connection:
            for table, rows in snapshots.items():
                assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "009"
    finally:
        engine.dispose()


def checkout(**overrides):
    return CheckoutSession(**{
        "id": "checkout", "user_id": "owner", "environment": "test",
        "idempotency_key": "key", "status": "pending", "product_id": "product",
        "plan_version": "v1", "amount_minor": 100, "currency": "USD",
        "limit_seconds": 600, "max_clip_seconds": 90, "success_url": "https://example.com",
        **overrides,
    })


@pytest.mark.parametrize("table", sorted(TABLES))
def test_009_downgrade_retains_every_kind_of_billing_history(migrated, table):
    url, engine = migrated
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(User(id="owner"))
        session.commit()
        if table == "billing_accounts":
            session.add(BillingAccount(id="account", user_id="owner", environment="test"))
        elif table == "checkout_sessions":
            session.add(checkout())
        elif table == "billing_subscriptions":
            session.add(checkout())
            session.flush()
            session.add(BillingSubscription(
                id="subscription", user_id="owner", environment="test", provider_id="sub",
                customer_id="customer", checkout_id="checkout", status="active",
                provider_updated_at=now,
            ))
        else:
            session.add(BillingWebhookEvent(
                id="event", environment="test", event_id="provider-event", event_type="paid",
                body_hash="hash", references="{}", next_attempt_at=now,
            ))
        session.commit()
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_alembic(url, "008")
    assert "Cannot remove billing identity or audit history" in error.value.stderr
    assert TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "009"


@pytest.mark.parametrize("status", ["creating", "pending", "uncertain"])
def test_009_open_checkout_index_blocks_duplicate_admission(migrated, status):
    from sqlalchemy.exc import IntegrityError

    _, engine = migrated
    with Session(engine) as session:
        session.add(User(id="owner"))
        session.commit()
        session.add(checkout(status=status))
        session.commit()
        session.add(checkout(id="second", idempotency_key="second", status=status))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(checkout(id="finished", idempotency_key="finished", status="completed"))
        session.add(checkout(id="live", idempotency_key="live", environment="live"))
        session.commit()
