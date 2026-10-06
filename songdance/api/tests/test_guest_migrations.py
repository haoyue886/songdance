import subprocess

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, GuestDay, GuestLedger, GuestSubmission, GuestTrial
from tests.test_dispatch_migrations import insert_legacy_job
from tests.test_migrations import run_alembic

TABLES = {"guest_trials", "guest_days", "guest_submissions", "guest_ledger"}
JOB_COLUMNS = {"guest_trial_id", "guest_reservation_id"}


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'guest.sqlite3'}"
    run_alembic(url, "011", direction="upgrade")
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def submission(**overrides):
    return GuestSubmission(**{
        "id": "submission", "trial_id": "trial", "submission_key": "key",
        "fingerprint": "fingerprint", "job_id": "deleted-job", "operation": "create",
        **overrides,
    })


def ledger(**overrides):
    return GuestLedger(**{
        "id": "ledger", "trial_id": "trial", "job_id": "deleted-job",
        "reservation_id": "reservation", "event_type": "reservation", **overrides,
    })


def test_011_schema_matches_models_and_empty_downgrade(migrated):
    url, engine = migrated
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, compare_to:
                name in TABLES | {"transcription_jobs"} if kind == "table" else True,
            "compare_server_default": True,
        })
        assert compare_metadata(context, Base.metadata) == []
    run_alembic(url, "010")
    assert not TABLES.intersection(inspect(engine).get_table_names())
    assert not JOB_COLUMNS.intersection({
        column["name"] for column in inspect(engine).get_columns("transcription_jobs")
    })
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "010"


def test_011_upgrade_and_downgrade_preserve_legacy_jobs(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    run_alembic(url, "010", direction="upgrade")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            insert_legacy_job(connection)
            connection.execute(text(
                "UPDATE transcription_jobs SET guest_secret_hash = 'legacy-secret'"
            ))
            old_columns = [column["name"] for column in inspect(connection).get_columns(
                "transcription_jobs"
            )]
            original = connection.execute(text("SELECT * FROM transcription_jobs")).one()
        run_alembic(url, "011", direction="upgrade")
        with engine.begin() as connection:
            columns = ",".join(old_columns)
            assert connection.execute(text(f"SELECT {columns} FROM transcription_jobs")).one() == (
                original
            )
            insert_legacy_job(connection, "post-upgrade")
            assert connection.execute(text(
                "SELECT guest_trial_id, guest_reservation_id FROM transcription_jobs"
            )).all() == [(None, None), (None, None)]
        run_alembic(url, "010")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM transcription_jobs")) == 2
            assert connection.execute(text(
                "SELECT * FROM transcription_jobs WHERE id = 'legacy'"
            )).one() == original
    finally:
        engine.dispose()


def test_011_indexes_and_foreign_keys_preserve_expired_task_history(migrated):
    _, engine = migrated
    inspector = inspect(engine)
    for table in ("guest_trials", "guest_days"):
        assert inspector.get_foreign_keys(table) == []
    for table in ("guest_submissions", "guest_ledger"):
        owners = inspector.get_foreign_keys(table)
        assert len(owners) == 1
        assert owners[0]["constrained_columns"] == ["trial_id"]
        assert owners[0]["referred_table"] == "guest_trials"
        assert owners[0]["options"]["ondelete"] == "RESTRICT"
    job_fks = inspector.get_foreign_keys("transcription_jobs")
    assert not any(JOB_COLUMNS.intersection(item["constrained_columns"]) for item in job_fks)
    indexes = {item["name"]: item for item in inspector.get_indexes("guest_ledger")}
    assert indexes["uq_guest_terminal"]["unique"] == 1
    assert str(indexes["uq_guest_terminal"]["dialect_options"]["sqlite_where"]) == (
        "event_type IN ('consume', 'release')"
    )
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys = ON"))
        connection.commit()
        with Session(bind=connection) as session:
            session.add(GuestTrial(id="trial"))
            session.commit()
            session.add_all([
                GuestDay(id="hashed-ip-day", day="2026-10-07", job_id="deleted-job"),
                submission(), ledger(),
            ])
            session.commit()
            with pytest.raises(IntegrityError):
                session.execute(text("DELETE FROM guest_trials WHERE id = 'trial'"))
                session.commit()
            session.rollback()


@pytest.mark.parametrize("terminal", ["consume", "release"])
def test_011_enforces_one_terminal_event_per_reservation(migrated, terminal):
    _, engine = migrated
    with Session(engine) as session:
        session.add(GuestTrial(id="trial"))
        session.commit()
        session.add_all([ledger(), ledger(id="terminal", event_type=terminal)])
        session.commit()
        other = "release" if terminal == "consume" else "consume"
        session.add(ledger(id="conflicting", event_type=other))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(ledger(id="duplicate", event_type=terminal))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(ledger(id="distinct", reservation_id="other", event_type=other))
        session.commit()


def test_011_submission_key_is_unique_within_trial(migrated):
    _, engine = migrated
    with Session(engine) as session:
        session.add_all([GuestTrial(id="trial"), GuestTrial(id="other")])
        session.commit()
        session.add(submission())
        session.commit()
        session.add(submission(id="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(submission(id="distinct", trial_id="other"))
        session.commit()


@pytest.mark.parametrize("history", sorted(TABLES | JOB_COLUMNS))
def test_011_downgrade_refuses_to_remove_guest_history(migrated, history):
    url, engine = migrated
    with Session(engine) as session:
        if history in JOB_COLUMNS:
            insert_legacy_job(session)
            session.execute(text(f"UPDATE transcription_jobs SET {history} = 'trial-history'"))
        elif history == "guest_days":
            session.add(GuestDay(id="hashed-ip-day", day="2026-10-07", job_id="deleted-job"))
        else:
            session.add(GuestTrial(id="trial"))
            session.commit()
            if history == "guest_submissions":
                session.add(submission())
            elif history == "guest_ledger":
                session.add(ledger())
        session.commit()
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_alembic(url, "010")
    assert "Cannot remove guest trial history or guest tasks" in error.value.stderr
    assert TABLES.issubset(inspect(engine).get_table_names())
    assert JOB_COLUMNS.issubset({
        column["name"] for column in inspect(engine).get_columns("transcription_jobs")
    })
    with engine.connect() as connection:
        table = "transcription_jobs" if history in JOB_COLUMNS else history
        assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "011"
