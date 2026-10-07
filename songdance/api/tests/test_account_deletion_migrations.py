import subprocess
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AccountDeletion,
    AccountDeletionSubscription,
    AuthIdentity,
    Base,
    GuestDay,
    GuestLedger,
    GuestSubmission,
    GuestTrial,
    UsageLedger,
    UsagePeriod,
    User,
)
from app.models.billing import BillingAccount, BillingSubscription, BillingWebhookEvent
from tests.test_billing_cancellation_migrations import cancellation, seed_paid
from tests.test_creem_migrations import checkout
from tests.test_dispatch_migrations import dispatch, insert_legacy_job, submission
from tests.test_migrations import run_alembic

TABLES = {"account_deletions", "account_deletion_subscriptions"}


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'account-deletions.sqlite3'}"
    run_alembic(url, "013", direction="upgrade")
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def deletion(**overrides):
    now = datetime.now(UTC)
    return AccountDeletion(**{
        "id": "deletion", "user_id": "owner", "auth_confirmed_at": now,
        "next_attempt_at": now, **overrides,
    })


def subscription(**overrides):
    return AccountDeletionSubscription(**{
        "id": "canceled-subscription", "deletion_id": "deletion", "environment": "test",
        "subscription_id": "provider-subscription", **overrides,
    })


def snapshot_history(connection):
    return {
        table: connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all()
        for table in set(inspect(connection).get_table_names()) - {"alembic_version"}
    }


def assert_history(connection, snapshots):
    for table, rows in snapshots.items():
        assert connection.execute(text(f"SELECT * FROM {table} ORDER BY id")).all() == rows


def test_013_schema_matches_models_and_empty_downgrade(migrated):
    url, engine = migrated
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, compare_to:
                name in TABLES if kind == "table" else True,
            "compare_server_default": True,
        })
        assert compare_metadata(context, Base.metadata) == []
    run_alembic(url, "012")
    assert not TABLES.intersection(inspect(engine).get_table_names())
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "012"


def test_013_upgrade_and_empty_downgrade_preserve_all_012_history(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    run_alembic(url, "012", direction="upgrade")
    engine = create_engine(url)
    now = datetime.now(UTC)
    try:
        with Session(engine) as session:
            paid = seed_paid(session)
            session.get(User, "owner").email = "retained@example.invalid"
            session.get(UsagePeriod, paid.usage_period_id).consumed_units = 30
            session.add_all([
                AuthIdentity(
                    id="identity", user_id="owner", issuer="verified-issuer", subject="subject",
                ),
                BillingAccount(
                    id="account", user_id="owner", environment="test", customer_id="customer",
                ),
                checkout(status="completed"),
                cancellation(paid, status="verified", attempts=2),
                UsageLedger(
                    id="usage-ledger", period_id=paid.usage_period_id, user_id="owner",
                    job_id="legacy", reservation_id="paid-reservation", event_type="consume",
                    units=30,
                ),
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
                submission(job_id="legacy"),
                dispatch(job_id="legacy"),
                GuestDay(id="ip-day", day="2026-10-07", job_id="legacy"),
                GuestSubmission(
                    id="guest-submission", trial_id="trial", submission_key="key",
                    fingerprint="hash", job_id="legacy", operation="create",
                ),
                GuestLedger(
                    id="guest-ledger", trial_id="trial", job_id="legacy",
                    reservation_id="guest-reservation", event_type="reservation",
                ),
            ])
            insert_legacy_job(session)
            session.execute(text(
                "UPDATE transcription_jobs SET owner_user_id = 'owner', "
                "guest_trial_id = 'trial', guest_reservation_id = 'guest-reservation' "
                "WHERE id = 'legacy'"
            ))
            session.commit()
        with engine.connect() as connection:
            snapshots = snapshot_history(connection)
        run_alembic(url, "013", direction="upgrade")
        assert set(inspect(engine).get_table_names()) == snapshots.keys() | TABLES | {
            "alembic_version"
        }
        with engine.connect() as connection:
            for table in TABLES:
                assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
            assert_history(connection, snapshots)
        run_alembic(url, "012")
        assert set(inspect(engine).get_table_names()) == snapshots.keys() | {"alembic_version"}
        with engine.connect() as connection:
            assert_history(connection, snapshots)
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "012"
    finally:
        engine.dispose()


def test_013_indexes_foreign_keys_and_unique_constraints(migrated):
    _, engine = migrated
    inspector = inspect(engine)
    for table, columns in {
        "account_deletions": ("status", "next_attempt_at"),
        "account_deletion_subscriptions": ("deletion_id",),
    }.items():
        assert {
            item["name"]: item["column_names"] for item in inspector.get_indexes(table)
        } == {f"ix_{table}_{column}": [column] for column in columns}
    for table, field, reference in (
        ("account_deletions", "user_id", "users"),
        ("account_deletion_subscriptions", "deletion_id", "account_deletions"),
    ):
        foreign_keys = inspector.get_foreign_keys(table)
        assert len(foreign_keys) == 1
        assert foreign_keys[0]["constrained_columns"] == [field]
        assert foreign_keys[0]["referred_table"] == reference
        assert foreign_keys[0]["referred_columns"] == ["id"]
        assert foreign_keys[0]["options"].get("ondelete") == "RESTRICT"
    assert inspector.get_unique_constraints("account_deletions") == [{
        "name": None, "column_names": ["user_id"],
    }]
    assert inspector.get_unique_constraints("account_deletion_subscriptions") == [{
        "name": "uq_account_deletion_subscription",
        "column_names": ["deletion_id", "environment", "subscription_id"],
    }]


@pytest.mark.parametrize("table", sorted(TABLES))
def test_013_foreign_keys_reject_missing_parent_and_preserve_history(migrated, table):
    _, engine = migrated
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.commit()
        with Session(bind=connection) as session:
            session.add(User(id="owner"))
            session.commit()
            is_request = table == "account_deletions"
            if not is_request:
                session.add(deletion())
                session.commit()
            factory = deletion if is_request else subscription
            field = "user_id" if is_request else "deletion_id"
            session.add(factory(**{field: "missing"}))
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()
            row = factory()
            session.add(row)
            session.commit()
            assert row.status == "pending"
            assert row.created_at is not None and row.updated_at is not None
            if is_request:
                assert (row.phase, row.attempts, row.retry_failures) == ("billing", 0, 0)
                assert row.completed_at is None and row.error_code is None
            else:
                assert row.provider_updated_at is None and row.verified_at is None
            parent = "users" if is_request else "account_deletions"
            with pytest.raises(IntegrityError):
                session.execute(
                    text(f"DELETE FROM {parent} WHERE id = :id"), {"id": getattr(row, field)},
                )
                session.commit()
            session.rollback()
            assert session.scalar(text(f"SELECT count(*) FROM {table}")) == 1


def test_013_request_is_unique_per_user(migrated):
    _, engine = migrated
    with Session(engine) as session:
        session.add_all([User(id="owner"), User(id="other")])
        session.commit()
        session.add(deletion())
        session.commit()
        session.add(deletion(id="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(deletion(id="other-deletion", user_id="other"))
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM account_deletions")) == 2


@pytest.mark.parametrize("variation", [
    {"environment": "live"}, {"subscription_id": "other-subscription"},
    {"deletion_id": "other-deletion"},
])
def test_013_subscription_is_unique_within_request_and_environment(migrated, variation):
    _, engine = migrated
    with Session(engine) as session:
        session.add_all([User(id="owner"), User(id="other")])
        session.commit()
        session.add_all([deletion(), deletion(id="other-deletion", user_id="other")])
        session.commit()
        session.add(subscription())
        session.commit()
        session.add(subscription(id="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(subscription(id="distinct", **variation))
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM account_deletion_subscriptions")) == 2


@pytest.mark.parametrize("table", sorted(TABLES))
@pytest.mark.parametrize("status", ["pending", "retry", "review", "completed"])
def test_013_downgrade_refuses_every_state_of_either_history_table(migrated, table, status):
    url, engine = migrated
    with engine.connect() as connection:
        # Protect restored subscription history even if its request is absent from a backup.
        connection.execute(text("PRAGMA foreign_keys = OFF"))
        connection.commit()
        with Session(bind=connection) as session:
            session.add(User(id="owner"))
            session.commit()
            if table == "account_deletions":
                session.add(deletion(
                    status=status, attempts=2, retry_failures=2, error_code="HISTORY",
                    completed_at=datetime.now(UTC) if status == "completed" else None,
                ))
            else:
                session.add(subscription(status=status))
            session.commit()
        snapshots = snapshot_history(connection)
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_alembic(url, "012")
    assert (
        "Cannot remove account deletion or subscription cancellation history" in error.value.stderr
    )
    assert set(inspect(engine).get_table_names()) == snapshots.keys() | {"alembic_version"}
    with engine.connect() as connection:
        assert_history(connection, snapshots)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "013"
