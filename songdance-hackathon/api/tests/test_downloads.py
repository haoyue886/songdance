import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.models import Artifact, TranscriptionJob, TranscriptionResult
from tests.conftest import wav_bytes


def signed_file(client, job_id: str, file_type: str):
    ticket = client.get(f"/jobs/{job_id}/download-url/{file_type}")
    assert ticket.status_code == 200
    return client.get(ticket.json()["path"])


def test_source_and_successful_artifact_download_real_bytes(api_client, tmp_path: Path) -> None:
    client, _, _ = api_client
    created = client.post(
        "/jobs",
        data={"start_sec": "0", "end_sec": "1", "rights_confirmed": "true"},
        files={"audio_file": ("piano.wav", wav_bytes(), "audio/wav")},
    )
    job_id = created.json()["id"]

    source = signed_file(client, job_id, "source")
    assert source.status_code == 200
    assert source.headers["content-type"] == "audio/wav"
    assert source.headers["content-disposition"].startswith("inline;")
    assert source.content[:4] == b"RIFF"

    artifact_bytes = b"MThd\x00\x00\x00\x06"
    artifact_path = tmp_path / "score.mid"
    artifact_path.write_bytes(artifact_bytes)
    storage_key = f"jobs/{job_id}/score.mid"
    client.app.state.storage.put_file(storage_key, artifact_path, "audio/midi")
    with client.app.state.session_factory() as session:
        session.add(
            Artifact(
                id=secrets.token_urlsafe(24),
                job_id=job_id,
                type="midi",
                status="succeeded",
                storage_key=storage_key,
                mime_type="audio/midi",
                size_bytes=len(artifact_bytes),
            )
        )
        session.add(
            TranscriptionResult(
                id=secrets.token_urlsafe(24),
                job_id=job_id,
                tempo=120.5,
                time_signature="4/4",
                note_count=24,
                quality_flags="[]",
                model_version="test-model",
            )
        )
        session.commit()

    job = client.get(f"/jobs/{job_id}").json()
    assert job["result"] == {
        "tempo": 120.5,
        "time_signature": "4/4",
        "note_count": 24,
        "quality_flags": "[]",
        "model_version": "test-model",
    }

    artifact = signed_file(client, job_id, "midi")
    assert artifact.status_code == 200
    assert artifact.headers["content-type"] == "audio/midi"
    assert artifact.headers["content-disposition"].startswith("attachment;")
    assert artifact.content == artifact_bytes


def test_failed_missing_and_unknown_artifacts_are_indistinguishable(api_client) -> None:
    client, _, _ = api_client
    created = client.post(
        "/jobs",
        data={"start_sec": "0", "end_sec": "1", "rights_confirmed": "true"},
        files={"audio_file": ("piano.wav", wav_bytes(), "audio/wav")},
    )
    job_id = created.json()["id"]
    with client.app.state.session_factory() as session:
        session.add(
            Artifact(
                id=secrets.token_urlsafe(24),
                job_id=job_id,
                type="musicxml",
                status="failed",
                storage_key=None,
                mime_type="application/vnd.recordare.musicxml+xml",
                size_bytes=0,
                error_code="MUSICXML_GENERATION_FAILED",
            )
        )
        session.commit()

    failed = client.get(f"/jobs/{job_id}/download-url/musicxml")
    missing = client.get(f"/jobs/{job_id}/download-url/midi")
    unknown = client.get(f"/jobs/{job_id}/download-url/not-real")
    unavailable_job = client.get("/jobs/not-real/download-url/midi")

    assert failed.status_code == missing.status_code == unknown.status_code == 404
    assert unavailable_job.status_code == 404


def test_expired_job_hides_metadata_source_and_artifacts(api_client) -> None:
    client, _, _ = api_client
    created = client.post(
        "/jobs",
        data={"start_sec": "0", "end_sec": "1", "rights_confirmed": "true"},
        files={"audio_file": ("piano.wav", wav_bytes(), "audio/wav")},
    )
    job_id = created.json()["id"]
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert client.get(f"/jobs/{job_id}/download-url/source").status_code == 404
    assert client.get(f"/jobs/{job_id}/download-url/midi").status_code == 404


def test_signed_download_rejects_tampering_and_expiration(api_client, monkeypatch) -> None:
    client, _, _ = api_client
    created = client.post(
        "/jobs",
        data={"start_sec": "0", "end_sec": "1", "rights_confirmed": "true"},
        files={"audio_file": ("piano.wav", wav_bytes(), "audio/wav")},
    )
    job_id = created.json()["id"]
    monkeypatch.setattr("app.services.downloads.time.time", lambda: 1_000)
    ticket = client.get(f"/jobs/{job_id}/download-url/source").json()
    assert "source.wav" not in ticket["path"]

    tampered = ticket["path"].replace("signature=", "signature=0", 1)
    assert client.get(tampered).status_code == 403

    monkeypatch.setattr("app.services.downloads.time.time", lambda: 1_301)
    expired = client.get(ticket["path"])
    assert expired.status_code == 403
    assert expired.json()["detail"] == "Download link is invalid or expired"
