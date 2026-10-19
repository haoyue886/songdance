"""Disposable PostgreSQL and real pipeline files; identity/provider calls stay offline."""

import os
import subprocess
import sys
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import (
    AccountDeletion,
    AuthIdentity,
    TranscriptionJob,
    UsageLedger,
    UsagePeriod,
    User,
)
from tests.test_account_deletion import create_job, process, request_deletion
from tests.test_account_deletion_real_services import client as client
from tests.test_auth_real_services import postgres as postgres
from tests.test_creem_billing import HEADERS
from tests.test_creem_real_services import database as database

pytestmark = pytest.mark.skipif(
    os.getenv("SONGDANCE_TEST_REAL_AUTH_SERVICES") != "1",
    reason="Opt in to disposable PostgreSQL; existing databases are never used",
)
API_ROOT = Path(__file__).resolve().parents[1]


def worker_environment(settings):
    # Both subprocesses run outside the repository, without its .env or provider credentials.
    return {
        **{
            key: value for key, value in os.environ.items()
            if not key.upper().startswith("SONGDANCE_")
        },
        "PYTHONPATH": str(API_ROOT),
        "SONGDANCE_ENVIRONMENT": "test",
        "SONGDANCE_DATABASE_URL": settings.database_url,
        "SONGDANCE_STORAGE_BACKEND": "local",
        "SONGDANCE_LOCAL_STORAGE_PATH": str(settings.local_storage_path),
        "SONGDANCE_TEMP_PATH": str(settings.temp_path),
        "SONGDANCE_QUOTA_BACKEND": "memory",
    }


def leave_interrupted_pipeline_files(state, job_id):
    # Abrupt exit skips TemporaryDirectory.__exit__. Directory creation, source download,
    # FFmpeg preprocessing and stage writes all use the production transcription entry point.
    script = """
import os
import sys
from app.database import create_db_engine, create_session_factory
from app.services import transcription
from app.services.storage import LocalObjectStorage
from app.settings import Settings

def stop_before_inference(*args, **kwargs):
    os._exit(73)

settings = Settings(_env_file=None)
engine = create_db_engine(settings)
transcription.transcribe_audio = stop_before_inference
transcription.run_transcription_job(
    sys.argv[1], settings, create_session_factory(engine),
    LocalObjectStorage(settings.local_storage_path), attempt=1,
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, job_id],
        cwd=state.settings.temp_path.parent,
        env=worker_environment(state.settings),
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 73, result.stdout + result.stderr
    directories = list(state.settings.temp_path.glob(f"pipeline-{job_id[:8]}-*"))
    assert len(directories) == 1
    directory = directories[0]
    assert (directory / "source.wav").is_file()
    with wave.open(str(directory / "normalized.wav"), "rb") as audio:
        assert audio.getframerate() == 22_050
        assert audio.getnframes() > 0
    with state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert (job.status, job.stage) == ("running", "transcribing")
    return directory


def run_deletion_worker(state, *, handled):
    result = subprocess.run(
        [sys.executable, "-m", "app.jobs.account_deletion", "--once"],
        cwd=state.settings.temp_path.parent,
        env=worker_environment(state.settings),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f'"handled":{handled}' in result.stderr


@pytest.mark.parametrize("cleanup_failure", [False, True])
def test_delete_cleans_actual_interrupted_pipeline_and_preserves_other_owner(
    client, monkeypatch, cleanup_failure
):
    import app.services.temp_cleanup as temp_cleanup

    state, provider = client.app.state, client.app.state.creem_client
    owner = client.get("/me", headers=HEADERS).json()["id"]
    bob_headers = {**HEADERS, "Authorization": "Bearer bob"}
    bob = client.get("/me", headers=bob_headers).json()["id"]
    created = create_job(client, "alice")
    other_created = create_job(client, "bob")
    assert created.status_code == other_created.status_code == 201
    job_id, other_id = created.json()["id"], other_created.json()["id"]
    assert job_id[:8] != other_id[:8]
    directory = leave_interrupted_pipeline_files(state, job_id)
    other_directory = leave_interrupted_pipeline_files(state, other_id)
    other_files = {path.name: path.read_bytes() for path in other_directory.iterdir()}
    unrelated = state.settings.temp_path / "unrelated.txt"
    unrelated.write_text("preserve unrelated files", encoding="utf8")

    accepted = request_deletion(client)
    assert accepted.status_code == 202
    identifier = accepted.json()["deletion"]["id"]
    run_deletion_worker(state, handled=1)
    with state.session_factory() as session:
        row = session.get(AccountDeletion, identifier)
        user = session.get(User, owner)
        assert (row.status, row.phase, row.attempts) == ("pending", "cleanup", 1)
        assert user.active is False and user.email is not None
        assert session.get(TranscriptionJob, job_id) is not None
    source_key = f"jobs/{job_id}/source.wav"
    assert state.storage.exists(source_key) and directory.is_dir()

    if cleanup_failure:
        original = temp_cleanup.shutil.rmtree

        def unavailable(path, *args, **kwargs):
            if Path(path) == directory:
                raise OSError("isolated pipeline directory is temporarily unavailable")
            return original(path, *args, **kwargs)

        with monkeypatch.context() as failure:
            failure.setattr(temp_cleanup.shutil, "rmtree", unavailable)
            assert process(client, provider) == 1
        with state.session_factory() as session:
            row = session.get(AccountDeletion, identifier)
            retained = session.get(TranscriptionJob, job_id)
            assert (row.status, row.phase, row.error_code) == (
                "retry", "cleanup", "DELETION_CLEANUP_RETRY",
            )
            assert row.completed_at is None and row.attempts == 2
            assert (retained.status, retained.error_code) == ("failed", "DELETE_FAILED")
            assert session.get(User, owner).email is not None
            retry_at = row.next_attempt_at
        assert directory.is_dir() and not state.storage.exists(source_key)
        run_deletion_worker(state, handled=0)
        assert process(client, provider, now=retry_at + timedelta(seconds=1)) == 1
    else:
        run_deletion_worker(state, handled=1)

    assert not directory.exists() and not state.storage.exists(source_key)
    assert {path.name: path.read_bytes() for path in other_directory.iterdir()} == other_files
    assert unrelated.read_text(encoding="utf8") == "preserve unrelated files"
    assert state.storage.exists(f"jobs/{other_id}/source.wav")
    with state.session_factory() as session:
        row = session.get(AccountDeletion, identifier)
        user = session.get(User, owner)
        assert (row.status, row.phase, row.attempts) == (
            "completed", "cleanup", 3 if cleanup_failure else 2,
        )
        assert row.completed_at is not None and row.error_code is None
        assert user.active is False and user.email is None
        assert session.get(TranscriptionJob, job_id) is None
        assert session.get(TranscriptionJob, other_id).status == "running"
        assert session.get(User, bob).active is True
        assert session.scalar(select(AuthIdentity).where(AuthIdentity.user_id == owner))
        owner_period = session.scalar(select(UsagePeriod).where(UsagePeriod.user_id == owner))
        bob_period = session.scalar(select(UsagePeriod).where(UsagePeriod.user_id == bob))
        assert (owner_period.reserved_units, owner_period.consumed_units) == (0, 0)
        assert (bob_period.reserved_units, bob_period.consumed_units) == (1, 0)
        assert sorted(session.scalars(select(UsageLedger.event_type).where(
            UsageLedger.user_id == owner,
        ))) == ["release", "reservation"]
    progress = client.get("/me", headers=HEADERS)
    assert progress.status_code == 200 and progress.json()["deletion"]["status"] == "completed"
    assert progress.json()["email"] is None
    assert client.get("/billing/me", headers=HEADERS).status_code == 403
    assert provider.cancel_calls == []
    assert process(client, provider, now=datetime.now(UTC) + timedelta(days=1)) == 0
