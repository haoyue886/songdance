"""Opt-in usage races against a fresh PostgreSQL cluster, never an existing service."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PaidPeriod, TranscriptionJob, UsageLedger, UsagePeriod, User
from app.services.entitlements import reserve_job, usage_summary
from app.services.paid_periods import PaidPeriodConflict, grant_paid_period
from app.services.usage import UsageExceeded, reserve_free, reserve_period, settle_job
from app.settings import Settings
from tests.test_auth_real_services import postgres as postgres

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to a temporary PostgreSQL instance; no existing services are used",
)


def migrate(database_url, revision):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={database_url}", "upgrade", revision],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "SONGDANCE_DATABASE_URL": database_url,
            "SONGDANCE_AUTH_ENABLED": "false",
            "SONGDANCE_USAGE_ENABLED": "false",
            "SONGDANCE_PAID_USAGE_ENABLED": "false",
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(scope="module")
def usage_postgres(postgres):
    admin, _ = postgres
    database_url = admin.replace("postgresql://", "postgresql+psycopg://")
    migrate(database_url, "007")
    engine = create_engine(
        database_url,
        connect_args={"options": "-c statement_timeout=10000 -c lock_timeout=8000"},
    )
    settings = Settings(free_monthly_job_limit=1).model_copy(
        update={"usage_enabled": True, "paid_usage_enabled": True, "billing_environment": "test"}
    )
    try:
        # Upgrade a populated 007 ledger; create_all would miss migration-only failures.
        with Session(engine) as session:
            legacy_user = User(id=str(uuid4()))
            session.add(legacy_user)
            session.flush()
            reservation = reserve_free(session, legacy_user, uuid4().hex, settings)
            legacy_user_id = legacy_user.id
            session.commit()
        migrate(database_url, "008")
        migrate(database_url, "009")
        yield engine, settings, legacy_user_id, reservation
    finally:
        engine.dispose()


def new_user(engine):
    user_id = str(uuid4())
    with Session(engine) as session:
        session.add(User(id=user_id))
        session.commit()
    return user_id


def grant(session, user_id, **overrides):
    now = datetime.now(UTC)
    facts = {
        "user_id": user_id,
        "environment": "test",
        "transaction_id": uuid4().hex,
        "subscription_id": uuid4().hex,
        "product_id": "postgres-test-product",
        "plan_version": "postgres-test-v1",
        "amount_minor": 990,
        "currency": "USD",
        "period_start": now - timedelta(days=1),
        "period_end": now + timedelta(days=29),
        "limit_seconds": 20,
    }
    return grant_paid_period(session, **(facts | overrides))


def test_008_migration_preserves_free_ledger_and_enforces_single_terminal(usage_postgres):
    engine, _, user_id, reservation_id = usage_postgres
    with Session(engine) as session:
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "009"
        assert session.scalar(text("SELECT to_regclass('public.paid_periods')")) == "paid_periods"
        period = session.scalars(select(UsagePeriod).where(UsagePeriod.user_id == user_id)).one()
        assert (period.limit_units, period.reserved_units, period.consumed_units) == (1, 1, 0)
        ledger = session.scalars(
            select(UsageLedger).where(UsageLedger.reservation_id == reservation_id)
        ).one()
        assert ledger.event_type == "reservation" and ledger.units == 1
        session.add(
            UsageLedger(
                id=uuid4().hex,
                period_id=period.id,
                user_id=user_id,
                reservation_id=reservation_id,
                event_type="consume",
                units=1,
            )
        )
        session.flush()
        with pytest.raises(IntegrityError) as error, session.begin_nested():
            session.add(
                UsageLedger(
                    id=uuid4().hex,
                    period_id=period.id,
                    user_id=user_id,
                    reservation_id=reservation_id,
                    event_type="release",
                    units=1,
                )
            )
            session.flush()
        assert error.value.orig.diag.constraint_name == "uq_usage_single_terminal"
        session.rollback()


@pytest.mark.parametrize("admission", [False, True], ids=["atomic-counter", "paid-admission"])
def test_twenty_seconds_accepts_only_one_concurrent_fifteen_second_reservation(
    usage_postgres, admission
):
    engine, settings, _, _ = usage_postgres
    user_id = new_user(engine)
    with Session(engine) as session:
        paid = grant(session, user_id)
        period_id = paid.usage_period_id
        session.commit()
    barrier = Barrier(2)

    def attempt(_):
        with Session(engine) as session:
            user = session.get(User, user_id)
            period = session.get(UsagePeriod, period_id)
            barrier.wait(timeout=5)
            try:
                if admission:
                    reserve_job(session, user, uuid4().hex, settings, duration=15)
                else:
                    reserve_period(session, period, uuid4().hex, 15)
                session.commit()
                return True
            except UsageExceeded:
                assert not admission
                session.rollback()
                return False
            except HTTPException as error:
                assert admission
                assert error.status_code == 429 and error.detail["code"] == "QUOTA_EXCEEDED"
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    with Session(engine) as session:
        period = session.get(UsagePeriod, period_id)
        assert (period.reserved_units, period.consumed_units) == (15, 0)
        entries = session.scalars(select(UsageLedger).where(UsageLedger.user_id == user_id)).all()
        assert len(entries) == 1 and entries[0].event_type == "reservation"
        assert entries[0].units == 15
        summary = usage_summary(session, session.get(User, user_id), settings)
        assert summary["plan"] == "pro" and summary["remaining"] == 5
        assert (
            session.scalar(
                select(UsagePeriod).where(
                    UsagePeriod.user_id == user_id, UsagePeriod.entitlement_type == "free_month"
                )
            )
            is None
        )


def test_consume_and_release_race_has_one_terminal_and_consistent_counters(usage_postgres):
    engine, _, _, _ = usage_postgres
    user_id, job_id = new_user(engine), uuid4().hex
    with Session(engine) as session:
        paid = grant(session, user_id)
        period_id = paid.usage_period_id
        reservation_id = reserve_period(session, session.get(UsagePeriod, period_id), job_id, 15)
        session.add(
            TranscriptionJob(
                id=job_id,
                owner_user_id=user_id,
                usage_reservation_id=reservation_id,
                start_sec=0,
                end_sec=15,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        session.commit()
    barrier = Barrier(2)

    def settle(success):
        with Session(engine) as session:
            job = session.get(TranscriptionJob, job_id)
            barrier.wait(timeout=5)
            changed = settle_job(session, job, success=success)
            session.commit()
            return changed

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(settle, [True, False])) == [False, True]
    with Session(engine) as session:
        entries = session.scalars(
            select(UsageLedger).where(UsageLedger.reservation_id == reservation_id)
        ).all()
        terminals = [entry for entry in entries if entry.event_type in {"consume", "release"}]
        assert len(entries) == 2 and len(terminals) == 1
        consumed = 15 if terminals[0].event_type == "consume" else 0
        period = session.get(UsagePeriod, period_id)
        assert (period.reserved_units, period.consumed_units) == (0, consumed)
        job = session.get(TranscriptionJob, job_id)
        assert not settle_job(session, job, success=True)
        assert not settle_job(session, job, success=False)
        session.commit()


def test_subscription_first_binding_race_cannot_split_between_users(usage_postgres):
    engine, _, _, _ = usage_postgres
    user_ids = [new_user(engine), new_user(engine)]
    subscription_id = uuid4().hex
    start = datetime.now(UTC)
    advisory_barrier = Barrier(2)
    advisory_calls = []

    def synchronize_advisory_calls(connection, cursor, statement, parameters, context, executemany):
        if "pg_advisory_xact_lock" in statement:
            advisory_calls.append(1)
            advisory_barrier.wait(timeout=5)

    def bind(index):
        with Session(engine) as session:
            try:
                # Distinct, nonoverlapping periods bypass subscription-period uniqueness.
                grant(
                    session,
                    user_ids[index],
                    subscription_id=subscription_id,
                    period_start=start + timedelta(days=30 * index),
                    period_end=start + timedelta(days=30 * (index + 1)),
                )
                session.commit()
                return True
            except PaidPeriodConflict as error:
                assert "another user" in str(error)
                session.rollback()
                return False

    event.listen(engine, "before_cursor_execute", synchronize_advisory_calls)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(bind, range(2))) == [False, True]
    finally:
        event.remove(engine, "before_cursor_execute", synchronize_advisory_calls)
    assert len(advisory_calls) == 2
    with Session(engine) as session:
        paid = session.scalars(
            select(PaidPeriod).where(PaidPeriod.subscription_id == subscription_id)
        ).one()
        usage = session.scalars(select(UsagePeriod).where(UsagePeriod.user_id.in_(user_ids))).one()
        assert usage.id == paid.usage_period_id and usage.user_id == paid.user_id


@pytest.mark.parametrize("admission", [False, True], ids=["free-period-creation", "free-admission"])
def test_free_month_accepts_only_one_concurrent_reservation(usage_postgres, admission):
    engine, settings, _, _ = usage_postgres
    user_id = new_user(engine)
    barrier = Barrier(2)

    def attempt(_):
        with Session(engine) as session:
            user = session.get(User, user_id)
            barrier.wait(timeout=5)
            try:
                if admission:
                    reserve_job(session, user, uuid4().hex, settings, duration=15)
                else:
                    reserve_free(session, user, uuid4().hex, settings)
                session.commit()
                return True
            except UsageExceeded:
                session.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    with Session(engine) as session:
        period = session.scalars(select(UsagePeriod).where(UsagePeriod.user_id == user_id)).one()
        assert period.entitlement_type == "free_month"
        assert (period.limit_units, period.reserved_units, period.consumed_units) == (1, 1, 0)
        entry = session.scalars(select(UsageLedger).where(UsageLedger.user_id == user_id)).one()
        assert entry.event_type == "reservation" and entry.units == 1
