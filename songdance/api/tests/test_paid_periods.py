from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import create_db_engine
from app.models import Base, UsagePeriod, User
from app.models.paid_period import PaidPeriod
from app.services.paid_periods import (
    PaidPeriodConflict,
    current_paid_period,
    grant_paid_period,
    set_paid_period_status,
)
from app.settings import Settings

START = datetime(2026, 1, 15, tzinfo=UTC)
END = datetime(2026, 2, 15, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path):
    engine = create_db_engine(Settings(database_url=f"sqlite:///{tmp_path / 'paid.sqlite3'}"))
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([User(id="alice"), User(id="bob")])
        session.commit()
        yield session
    engine.dispose()


def grant(session: Session, **overrides) -> PaidPeriod:
    facts = dict(
        user_id="alice",
        environment="test",
        transaction_id="txn_1",
        subscription_id="sub_1",
        product_id="prod_1",
        plan_version="pro-test-v1",
        amount_minor=990,
        currency="USD",
        period_start=START,
        period_end=END,
    )
    facts.update(overrides)
    return grant_paid_period(session, **facts)


def test_replay_preserves_usage_and_revoked_status(session: Session) -> None:
    paid = grant(session)
    usage = session.get(UsagePeriod, paid.usage_period_id)
    assert usage is not None and usage.entitlement_type == "pro_paid"
    assert usage.limit_units == 1800 and paid.max_clip_seconds == 90
    usage.consumed_units, usage.reserved_units = 135, 31
    set_paid_period_status(
        session, user_id="alice", environment="test", transaction_id="txn_1", status="revoked"
    )
    session.commit()
    session.expire_all()
    replay = grant(session)
    assert replay.id == paid.id and replay.status == "revoked"
    assert (usage.consumed_units, usage.reserved_units) == (135, 31)
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 1
    assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"user_id": "bob"},
        {"subscription_id": "other"},
        {"product_id": "other"},
        {"plan_version": "v2"},
        {"amount_minor": 991},
        {"currency": "EUR"},
        {"period_start": START + timedelta(seconds=1)},
        {"period_end": END + timedelta(seconds=1)},
        {"limit_seconds": 1801},
        {"max_clip_seconds": 89},
    ],
)
def test_conflicting_transaction_replay_rejected(session: Session, overrides: dict) -> None:
    grant(session)
    with pytest.raises(PaidPeriodConflict):
        grant(session, **overrides)
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 1


def test_same_subscription_cannot_move_to_another_user(session: Session) -> None:
    grant(session)
    with pytest.raises(PaidPeriodConflict, match="another user"):
        grant(
            session,
            user_id="bob",
            transaction_id="txn_2",
            period_start=END,
            period_end=datetime(2026, 3, 15, tzinfo=UTC),
        )


@pytest.mark.parametrize("status", ["active", "frozen", "revoked"])
def test_overlapping_paid_coverage_rejected_in_all_states(session: Session, status: str) -> None:
    grant(session)
    if status != "active":
        set_paid_period_status(
            session, user_id="alice", environment="test", transaction_id="txn_1", status=status
        )
    with pytest.raises(PaidPeriodConflict, match="overlaps"):
        grant(
            session,
            transaction_id="txn_2",
            subscription_id="sub_2",
            period_start=END - timedelta(seconds=1),
            period_end=END + timedelta(days=20),
        )


def test_environment_namespace_isolation(session: Session) -> None:
    test = grant(session)
    assert current_paid_period(session, user_id="alice", environment="live", now=START) is None
    live = grant(session, environment="live", product_id="prod_live")
    assert test.id != live.id and test.usage_period_id != live.usage_period_id
    set_paid_period_status(
        session, user_id="alice", environment="test", transaction_id="txn_1", status="frozen"
    )
    assert current_paid_period(session, user_id="alice", environment="test", now=START) == test
    assert current_paid_period(session, user_id="alice", environment="live", now=START) == live
    assert test.status == "frozen" and live.status == "active"
    assert current_paid_period(session, user_id="bob", environment="live", now=START) is None


def test_period_boundaries_and_old_transaction_revocation(session: Session) -> None:
    old = grant(session)
    new_end = datetime(2026, 3, 15, tzinfo=UTC)
    new = grant(session, transaction_id="txn_2", period_start=END, period_end=new_end)
    assert (
        current_paid_period(
            session, user_id="alice", environment="test", now=START - timedelta(microseconds=1)
        )
        is None
    )
    assert current_paid_period(session, user_id="alice", environment="test", now=START) == old
    assert current_paid_period(session, user_id="alice", environment="test", now=END) == new
    for status in ("frozen", "revoked", "frozen"):
        set_paid_period_status(
            session, user_id="alice", environment="test", transaction_id="txn_1", status=status
        )
    assert old.status == "revoked" and new.status == "active"
    assert current_paid_period(session, user_id="alice", environment="test", now=START) == old
    assert current_paid_period(session, user_id="alice", environment="test", now=END) == new
    assert current_paid_period(session, user_id="alice", environment="test", now=new_end) is None
    assert session.get(UsagePeriod, new.usage_period_id).consumed_units == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "production"},
        {"transaction_id": ""},
        {"transaction_id": "x" * 256},
        {"subscription_id": "  sub"},
        {"product_id": "\n"},
        {"plan_version": "x" * 65},
        {"amount_minor": 0},
        {"amount_minor": 1.1},
        {"amount_minor": True},
        {"amount_minor": 2**31},
        {"limit_seconds": -1},
        {"limit_seconds": False},
        {"currency": "usd"},
        {"currency": "USDD"},
        {"period_start": START.replace(tzinfo=None)},
        {"period_end": START},
        {"max_clip_seconds": 91},
        {"max_clip_seconds": 300},
        {"max_clip_seconds": 0},
        {"user_id": "missing"},
    ],
)
def test_invalid_facts_never_create_entitlement(session: Session, overrides: dict) -> None:
    with pytest.raises(ValueError):
        grant(session, **overrides)
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 0
    assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 0


def test_timezone_normalized_replay(session: Session) -> None:
    paid = grant(session)
    session.commit()
    session.expire_all()
    offset = timezone(timedelta(hours=8))
    assert (
        grant(session, period_start=START.astimezone(offset), period_end=END.astimezone(offset)).id
        == paid.id
    )


@pytest.mark.parametrize("user_id,environment", [("bob", "test"), ("alice", "live")])
def test_status_update_requires_exact_user_and_environment(
    session: Session,
    user_id: str,
    environment: str,
) -> None:
    paid = grant(session)
    with pytest.raises(PaidPeriodConflict):
        set_paid_period_status(
            session,
            user_id=user_id,
            environment=environment,
            transaction_id="txn_1",
            status="revoked",
        )
    assert paid.status == "active"


def test_rollback_does_not_leave_grant_or_quota(session: Session) -> None:
    grant(session)
    session.rollback()
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 0
    assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 0


def test_concurrent_duplicate_facts_create_one_grant(session: Session) -> None:
    engine = session.get_bind()
    barrier = Barrier(2)

    def persist() -> str:
        with Session(engine) as local:
            barrier.wait(timeout=5)
            paid = grant(local)
            paid_id = paid.id
            local.commit()
            return paid_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(persist) for _ in range(2)]
        ids = [future.result(timeout=10) for future in pending]
    assert ids[0] == ids[1]
    assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 1
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 1


def test_concurrent_overlapping_facts_allow_only_one_grant(session: Session) -> None:
    engine = session.get_bind()
    barrier = Barrier(2)

    def persist(transaction_id: str) -> bool:
        with Session(engine) as local:
            barrier.wait(timeout=5)
            try:
                grant(local, transaction_id=transaction_id)
                local.commit()
                return True
            except PaidPeriodConflict:
                local.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(persist, f"txn_{index}") for index in range(2)]
        results = [future.result(timeout=10) for future in pending]
    assert sorted(results) == [False, True]
    assert session.scalar(select(func.count()).select_from(UsagePeriod)) == 1


def test_concurrent_subscription_binding_cannot_split_between_users(session: Session) -> None:
    engine = session.get_bind()
    barrier = Barrier(2)

    def persist(user_id: str, start: datetime, end: datetime) -> bool:
        with Session(engine) as local:
            barrier.wait(timeout=5)
            try:
                grant(
                    local,
                    user_id=user_id,
                    transaction_id=f"txn_{user_id}",
                    period_start=start,
                    period_end=end,
                )
                local.commit()
                return True
            except PaidPeriodConflict:
                local.rollback()
                return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [
            pool.submit(persist, "alice", START, END),
            pool.submit(persist, "bob", END, datetime(2026, 3, 15, tzinfo=UTC)),
        ]
        results = [future.result(timeout=10) for future in pending]
    assert sorted(results) == [False, True]
    assert session.scalar(select(func.count()).select_from(PaidPeriod)) == 1


@pytest.mark.parametrize(
    "change",
    [
        {"environment": "production"},
        {"status": "canceled"},
        {"max_clip_seconds": 300},
        {"amount_minor": 0},
        {"period_end": START},
    ],
)
def test_database_rejects_invalid_persisted_facts(session: Session, change: dict) -> None:
    paid = grant(session)
    session.commit()
    for key, value in change.items():
        setattr(paid, key, value)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_database_enforces_transaction_and_period_uniqueness(session: Session) -> None:
    paid = grant(session)
    session.commit()
    facts = {column.name: getattr(paid, column.name) for column in PaidPeriod.__table__.columns}
    for overrides in (
        {"id": "duplicate-transaction", "subscription_id": "different"},
        {"id": "duplicate-period", "transaction_id": "different"},
    ):
        usage = UsagePeriod(
            id=overrides["id"],
            user_id="alice",
            entitlement_type="pro_paid",
            period_key=overrides["id"],
            period_start=START,
            period_end=END,
            limit_units=1800,
        )
        session.add(usage)
        session.flush()
        session.add(PaidPeriod(**(facts | overrides | {"usage_period_id": usage.id})))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()
