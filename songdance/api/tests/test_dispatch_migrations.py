import subprocess
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base, JobDispatch, JobSubmission, TranscriptionJob, User
from tests.test_migrations import run_alembic

TABLES = {"job_submissions", "job_dispatches"}


@pytest.fixture
def migrated(tmp_path):
    url = f"sqlite:///{tmp_path / 'dispatch.sqlite3'}"
    run_alembic(url, "010", direction="upgrade")
    engine = create_engine(url)
    try:
        yield url, engine
    finally:
        engine.dispose()


def insert_legacy_job(connection, job_id="legacy"):
    connection.execute(text(
        "INSERT INTO transcription_jobs "
        "(id,status,stage,source_type,start_sec,end_sec,attempt_count,expires_at) "
        "VALUES (:id,'queued','queued','upload',0,15,1,'2026-10-07')"
    ), {"id": job_id})


def submission(**overrides):
    return JobSubmission(**{
        "id": "submission", "user_id": "owner", "submission_key": "key",
        "fingerprint": "fingerprint", "job_id": "deleted-job", "attempt": 1,
        "operation": "create", **overrides,
    })


def dispatch(**overrides):
    now = datetime.now(UTC)
    return JobDispatch(**{
        "id": "dispatch", "job_id": "deleted-job", "attempt": 1,
        "next_attempt_at": now, "deadline_at": now, **overrides,
    })


def test_010_upgrade_preserves_legacy_jobs_and_default_false(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    run_alembic(url, "009", direction="upgrade")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            insert_legacy_job(connection)
            old_columns = [column["name"] for column in inspect(connection).get_columns(
                "transcription_jobs"
            )]
            original = connection.execute(text("SELECT * FROM transcription_jobs")).one()
        run_alembic(url, "010", direction="upgrade")
        with engine.begin() as connection:
            columns = ",".join(old_columns)
            assert connection.execute(text(f"SELECT {columns} FROM transcription_jobs")).one() == (
                original
            )
            insert_legacy_job(connection, "post-upgrade")
        with Session(engine) as session:
            jobs = session.scalars(select(TranscriptionJob)).all()
            assert len(jobs) == 2
            assert all(job.dispatch_managed is False for job in jobs)
        run_alembic(url, "009")
        assert not TABLES.intersection(inspect(engine).get_table_names())
        assert "dispatch_managed" not in {
            column["name"] for column in inspect(engine).get_columns("transcription_jobs")
        }
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM transcription_jobs")) == 2
    finally:
        engine.dispose()


def test_010_schema_matches_models_and_empty_downgrade(migrated):
    url, engine = migrated
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={
            "include_object": lambda obj, name, kind, reflected, compare_to:
                name in TABLES | {"transcription_jobs"} if kind == "table" else True,
            "compare_server_default": True,
        })
        assert compare_metadata(context, Base.metadata) == []
    run_alembic(url, "009")
    assert not TABLES.intersection(inspect(engine).get_table_names())
    assert "dispatch_managed" not in {
        column["name"] for column in inspect(engine).get_columns("transcription_jobs")
    }
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "009"


def test_010_indexes_and_foreign_keys(migrated):
    _, engine = migrated
    inspector = inspect(engine)
    for table, columns in {
        "job_submissions": ("user_id", "job_id"),
        "job_dispatches": ("job_id", "status", "next_attempt_at"),
    }.items():
        indexes = {item["name"]: item["column_names"] for item in inspector.get_indexes(table)}
        assert indexes == {f"ix_{table}_{column}": [column] for column in columns}
    assert inspector.get_foreign_keys("job_dispatches") == []
    owners = inspector.get_foreign_keys("job_submissions")
    assert len(owners) == 1
    assert owners[0]["constrained_columns"] == ["user_id"]
    assert owners[0]["referred_table"] == "users"
    assert owners[0]["options"]["ondelete"] == "RESTRICT"


@pytest.mark.parametrize("kind", ["submission", "dispatch"])
def test_010_unique_constraints_enforce_idempotency(migrated, kind):
    _, engine = migrated
    with Session(engine) as session:
        session.add_all([User(id="owner"), User(id="other")])
        session.commit()
        factory = submission if kind == "submission" else dispatch
        session.add(factory())
        session.commit()
        session.add(factory(id="duplicate"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        variation = {"user_id": "other"} if kind == "submission" else {"attempt": 2}
        session.add(factory(id="distinct", **variation))
        session.commit()


@pytest.mark.parametrize("history", ["job_submissions", "job_dispatches", "managed_job"])
def test_010_downgrade_refuses_to_remove_history(migrated, history):
    url, engine = migrated
    with Session(engine) as session:
        session.add(User(id="owner"))
        session.commit()
        if history == "job_submissions":
            session.add(submission())
        elif history == "job_dispatches":
            session.add(dispatch())
        else:
            insert_legacy_job(session)
            session.execute(text("UPDATE transcription_jobs SET dispatch_managed = true"))
        session.commit()
    with pytest.raises(subprocess.CalledProcessError) as error:
        run_alembic(url, "009")
    assert "Cannot remove submission or dispatch history or managed tasks" in error.value.stderr
    assert TABLES.issubset(inspect(engine).get_table_names())
    with engine.connect() as connection:
        table = "transcription_jobs" if history == "managed_job" else history
        assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "010"
        assert "dispatch_managed" in {
            column["name"] for column in inspect(connection).get_columns("transcription_jobs")
        }
