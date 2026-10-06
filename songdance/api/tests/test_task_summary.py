from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Base, TranscriptionJob, UsageLedger, UsagePeriod, User
from app.services.task_summary import task_summary


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'summary.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [User(id="alice", email="alice@test.invalid"), User(id="bob", email="bob@test.invalid")]
        )
        session.flush()
        yield session
    engine.dispose()


def period(session, identifier="current", owner="alice", kind="free_month", month=10):
    value = UsagePeriod(
        id=identifier,
        user_id=owner,
        entitlement_type=kind,
        period_key=identifier,
        period_start=datetime(2026, month, 1, tzinfo=UTC),
        period_end=datetime(2026, month + 1, 1, tzinfo=UTC),
        limit_units=1800,
    )
    session.add(value)
    session.flush()
    return value


def attempt(session, usage_period, job_id, terminal=None, reason="worker", units=1):
    reservation = str(uuid4())
    for event in ["reservation"] + ([terminal] if terminal else []):
        session.add(
            UsageLedger(
                id=str(uuid4()),
                user_id=usage_period.user_id,
                period_id=usage_period.id,
                job_id=job_id,
                reservation_id=reservation,
                event_type=event,
                units=units,
                details='{"source":"' + reason + '"}',
                # A late settlement must still count in the reservation's period.
                created_at=usage_period.period_end + timedelta(hours=1),
            )
        )
    session.flush()


def test_retries_count_once_and_follow_consumption_then_pending_then_release(session):
    current = period(session)
    attempt(session, current, "success", "release")
    attempt(session, current, "success", "consume")
    attempt(session, current, "success")
    attempt(session, current, "retrying", "release")
    attempt(session, current, "retrying")
    attempt(session, current, "failed", "release")
    attempt(session, current, "failed", "release")
    attempt(session, current, "cancelled", "release", reason="user_delete")

    assert task_summary(session, "alice", current.id) == {
        "succeeded": 1,
        "failed": 2,
        "in_progress": 1,
    }


def test_summary_filters_owner_and_exact_entitlement_period_not_event_date(session):
    current = period(session)
    same_dates_pro = period(session, "pro", kind="pro_paid")
    old = period(session, "old", month=9)
    other_user = period(session, "bob-current", owner="bob")
    attempt(session, current, "free-success", "consume")
    attempt(session, same_dates_pro, "pro-running", units=90)
    attempt(session, old, "old-failure", "release")
    attempt(session, other_user, "bob-success", "consume")

    assert task_summary(session, "alice", current.id) == {
        "succeeded": 1,
        "failed": 0,
        "in_progress": 0,
    }
    assert task_summary(session, "alice", same_dates_pro.id) == {
        "succeeded": 0,
        "failed": 0,
        "in_progress": 1,
    }
    assert task_summary(session, "alice", old.id) == {
        "succeeded": 0,
        "failed": 1,
        "in_progress": 0,
    }
    assert task_summary(session, "alice", other_user.id) == {
        "succeeded": 0,
        "failed": 0,
        "in_progress": 0,
    }


def test_cleanup_keeps_counts_and_claimed_unmetered_jobs_are_not_counted(session):
    current = period(session)
    job = TranscriptionJob(
        id="cleaned",
        owner_user_id="alice",
        start_sec=0,
        end_sec=1,
        expires_at=datetime.now(UTC),
    )
    claimed = TranscriptionJob(
        id="claimed-guest",
        owner_user_id="alice",
        status="succeeded",
        start_sec=0,
        end_sec=1,
        expires_at=datetime.now(UTC),
    )
    session.add_all([job, claimed])
    attempt(session, current, job.id, "consume")
    session.delete(job)
    session.flush()

    assert task_summary(session, "alice", current.id) == {
        "succeeded": 1,
        "failed": 0,
        "in_progress": 0,
    }


def test_no_period_no_tasks_and_non_task_adjustments_are_zero(session):
    current = period(session)
    attempt(session, current, None, "consume")
    session.add(
        UsageLedger(
            id="adjustment",
            user_id="alice",
            period_id=current.id,
            job_id="adjusted",
            reservation_id="adjustment",
            event_type="adjustment",
            units=1,
        )
    )
    for period_id in [None, "missing", current.id]:
        assert task_summary(session, "alice", period_id) == {
            "succeeded": 0,
            "failed": 0,
            "in_progress": 0,
        }
