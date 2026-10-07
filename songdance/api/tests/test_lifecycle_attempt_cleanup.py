"""Remove PUTs whose Worker died before recording artifact outcomes."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs.cleanup import cleanup_expired_jobs
from app.models import AccountDeletion, Artifact, TranscriptionJob
from app.services.account_deletion import process_account_deletions
from app.services.transcription_artifacts import write_and_store_artifact
from tests.test_auth_ownership import create_job
from tests.test_auth_ownership import protected_client as protected_client

OWNER = {"Authorization": "Bearer alice"}


@pytest.mark.parametrize("operation", ["account", "manual", "expiry"])
def test_all_attempt_uploads_are_removed_without_deleting_other_jobs(
    protected_client, tmp_path, operation
):
    client = protected_client
    job_id = create_job(client, "alice").json()["id"]
    other = create_job(client, "bob").json()["id"]
    state = client.app.state
    path = tmp_path / "unregistered.json"
    orphaned = []

    def put(job_id, attempt):
        outcome = write_and_store_artifact(
            state.session_factory,
            state.storage,
            job_id,
            attempt,
            "raw_timeline",
            path,
            lambda: path.write_text('{"notes":[]}', encoding="utf8"),
        )
        assert outcome.status == "succeeded" and state.storage.exists(outcome.storage_key)
        return outcome.storage_key

    for attempt in (1, 2, 3):
        with state.session_factory.begin() as session:
            session.get(TranscriptionJob, job_id).attempt_count = attempt
        orphaned.append(put(job_id, attempt))
    preserved = put(other, 1)
    with state.session_factory() as session:
        assert session.scalar(select(Artifact)) is None
    if operation == "account":
        state.settings.account_deletion_enabled = True
        state.settings.usage_enabled = state.settings.reliable_queue_enabled = True
        state.auth_verifier.reauthenticated_at = lambda _: datetime.now(UTC)
        assert (
            client.request(
                "DELETE",
                "/me",
                headers={**OWNER, "Origin": "http://localhost:3000"},
                json={"confirmation": "DELETE"},
            ).status_code
            == 202
        )
        for _ in range(2):
            process_account_deletions(
                state.session_factory,
                state.storage,
                state.settings,
                quota=state.job_quota,
            )
        with state.session_factory() as session:
            assert session.scalar(select(AccountDeletion)).status == "completed"
    elif operation == "manual":
        assert client.delete(f"/jobs/{job_id}", headers=OWNER).status_code == 204
    else:
        with state.session_factory.begin() as session:
            session.get(TranscriptionJob, job_id).expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
        result = cleanup_expired_jobs(
            state.session_factory,
            state.storage,
            state.settings,
            job_quota=state.job_quota,
        )
        assert (result.deleted, result.failed) == (1, 0)
    with state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
        assert session.get(TranscriptionJob, other) is not None
    assert all(not state.storage.exists(key) for key in orphaned)
    assert state.storage.exists(preserved)
