import subprocess
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, GuestDay, GuestLedger, GuestSubmission, GuestTrial, User
from app.models.billing import (
    BillingAccount,
    BillingCancellation,
    BillingSubscription,
    BillingWebhookEvent,
)
from tests.test_creem_migrations import checkout
from tests.test_dispatch_migrations import insert_legacy_job
from tests.test_entitlements import grant
from tests.test_migrations import run_alembic

TABLE = "billing_cancellations"


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'cancellations.sqlite3'}"
    run_alembic(url, "012", direction="upgrade")
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def cancellation(paid, **overrides):
    return BillingCancellation(**{
        "id": "cancellation", "user_id": paid.user_id, "environment": paid.environment,
        "paid_period_id": paid.id, "subscription_id": paid.subscription_id,
        "transaction_id": paid.transaction_id, "next_attempt_at": datetime.now(UTC),
        **overrides,
    })


def seed_paid(session):
    session.add(User(id="owner"))
    session.commit()
    paid = grant(session, "owner")
    session.commit()
    return paid


def test_012_schema_matches_models_and_empty_downgrade(migrated):
    url, engine = migrated
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, compare_to:
                name == TABLE if kind == "table" else True,
            "compare_server_default": True,
        })
        assert compare_metadata(context, Base.metadata) == []
    run_alembic(url, "011")
    assert TABLE not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "011"


def test_012_upgrade_and_empty_downgrade_preserve_011_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    run_alembic(url, "011", direction="upgrade")
    engine = create_engine(url)
    now = datetime.now(UTC)
    try:
        with Session(engine) as session:
            paid = seed_paid(session)
            session.add_all([
                BillingAccount(id="account", user_id="owner", environment="test"),
                checkout(status="completed"),
                GuestTrial(id="trial", reserved=1),
            ])
            session.commit()
            session.add_all([
                BillingSubscription(
                    id="subscription", user_id="owner", environment="test",
                    provider_id=paid.subscription_id, customer_id="customer",
                    checkout_id="checkout", status="active", provider_updated_at=now,
                ),
                BillingWebhookEvent(
                    id="event", environment="test", event_id="provider-event", event_type="paid",
                    body_hash="hash", references="{}", next_attempt_at=now,
                ),
                GuestDay(id="ip-day", day="2026-10-07", job_id="legacy"),
                GuestSubmission(
                    id="submission", trial_id="trial", submission_key="key",
                    fingerprint="hash", job_id="legacy", operation="create",
                ),
                GuestLedger(
                    id="ledger", trial_id="trial", job_id="legacy",
                    reservation_id="reservation", event_type="reservation",
                ),
            ])
            insert_legacy_job(session)
            session.execute(text(
                "UPDATE transcription_jobs SET guest_trial_id = 'trial', "
                "guest_reservation_id = 'reservation' WHERE id = 'legacy'"
            ))
            session.commit()
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names()) - {"alembic_version"}
            snapshots = {
                table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
                for table in tables
            }
        run_alembic(url, "012", direction="upgrade")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM billing_cancellations")) == 0
            for table, rows in snapshots.items():
                assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
        run_alembic(url, "011")
        assert set(inspect(engine).get_table_names()) == tables | {"alembic_version"}
        with engine.connect() as connection:
            for table, rows in snapshots.items():
                assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "011"
    finally:
        engine.dispose()


def test_012_indexes_and_foreign_keys(migrated):
    _, engine = migrated
    inspector = inspect(engine)
    foreign_keys = inspector.get_foreign_keys(TABLE)
    assert {
        (tuple(item["constrained_columns"]), item["referred_table"],
         tuple(item["referred_columns"]), item["options"].get("ondelete"))
        for item in foreign_keys
    } == {
        (("user_id",), "users", ("id",), "RESTRICT"),
        (("paid_period_id",), "paid_periods", ("id",), "RESTRICT"),
    }
    assert {
        item["name"]: item["column_names"] for item in inspector.get_indexes(TABLE)
    } == {
        f"ix_billing_cancellations_{column}": [column]
        for column in ("user_id", "paid_period_id", "status", "next_attempt_at")
    }
    assert inspector.get_unique_constraints(TABLE) == [{
        "name": "uq_billing_cancellation", "column_names": ["environment", "transaction_id"],
    }]


@pytest.mark.parametrize("field", ["user_id", "paid_period_id"])
def test_012_rejects_missing_foreign_keys_and_retains_paid_history(migrated, field):
    _, engine = migrated
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.commit()
        with Session(bind=connection) as session:
            paid = seed_paid(session)
            session.add(cancellation(paid, **{field: "missing"}))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            row = cancellation(paid)
            session.add(row)
            session.commit()
            assert (row.status, row.attempts, row.error_code) == ("pending", 0, None)
            assert row.created_at is not None and row.updated_at is not None
            with pytest.raises(IntegrityError):
                session.execute(text("DELETE FROM paid_periods WHERE id = :id"), {"id": paid.id})
                session.commit()
            session.rollback()
            assert session.scalar(text("SELECT count(*) FROM billing_cancellations")) == 1


def test_012_transaction_unique_within_environment(migrated):
    _, engine = migrated
    with Session(engine) as session:
        paid = seed_paid(session)
        session.add(cancellation(paid))
        session.commit()
        session.add(cancellation(paid, id="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        live = grant(session, "owner", environment="live")
        session.add(cancellation(live, id="live"))
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM billing_cancellations")) == 2


@pytest.mark.parametrize("status", ["pending", "retry", "verified", "review"])
def test_012_downgrade_refuses_any_cancellation_history(migrated, status):
    url, engine = migrated
    with Session(engine) as session:
        paid = seed_paid(session)
        session.add(cancellation(paid, status=status, attempts=2, error_code="HISTORY"))
        session.commit()
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        snapshots = {
            table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
            for table in tables - {"alembic_version"}
        }
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_alembic(url, "011")
    assert "Cannot remove billing cancellation history" in error.value.stderr
    assert set(inspect(engine).get_table_names()) == tables
    with engine.connect() as connection:
        for table, rows in snapshots.items():
            assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "012"
