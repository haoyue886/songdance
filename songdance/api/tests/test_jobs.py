import subprocess
import wave
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Artifact, JobStatus, TranscriptionJob
from tests.conftest import wav_bytes


class FailingSecondDeleteStorage:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.delete_count = 0

    def delete(self, key: str) -> None:
        self.delete_count += 1
        if self.delete_count == 2:
            raise ConnectionError("object storage unavailable")
        self.delegate.delete(key)


def create_job(client: TestClient, **overrides: object):
    data: dict[str, object] = {
        "start_sec": "0",
        "end_sec": "1.5",
        "rights_confirmed": "true",
    }
    data.update(overrides.pop("data", {}))
    files = overrides.pop("files", {"audio_file": ("piano.wav", wav_bytes(), "audio/wav")})
    return client.post("/jobs", data=data, files=files, **overrides)


def mark_failed(client: TestClient, job_id: str, attempt_count: int) -> None:
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.status = JobStatus.FAILED
        job.error_code = "MODEL_FAILED"
        job.error_message = "模型处理失败"
        job.attempt_count = attempt_count
        session.commit()


def test_create_and_query_job_does_not_enqueue_twice(api_client) -> None:
    client, queue, storage_path = api_client

    response = create_job(client)

    assert response.status_code == 201
    payload = response.json()
    assert len(payload["id"]) >= 32
    assert payload["status"] == "queued"
    assert payload["stage"] == "queued"
    assert payload["attempt_count"] == 1
    assert payload["end_sec"] == 1.5
    assert queue.calls == [(payload["id"], 1)]
    assert len(list(storage_path.rglob("source.wav"))) == 1

    first_query = client.get(f"/jobs/{payload['id']}")
    second_query = client.get(f"/jobs/{payload['id']}")
    assert first_query.status_code == second_query.status_code == 200
    assert first_query.json() == second_query.json()
    assert queue.calls == [(payload["id"], 1)]


def test_create_stores_only_the_selected_clip(api_client) -> None:
    client, _queue, storage_path = api_client

    response = create_job(
        client,
        data={"start_sec": "2", "end_sec": "3.5"},
        files={"audio_file": ("long.wav", wav_bytes(duration=5), "audio/wav")},
    )

    assert response.status_code == 201
    stored = next(storage_path.rglob("source.wav"))
    with wave.open(str(stored), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 44_100
        assert audio.getnframes() / audio.getframerate() == 1.5


def test_create_rejects_rights_signature_mime_and_clip(api_client) -> None:
    client, queue, _storage_path = api_client

    no_rights = create_job(client, data={"rights_confirmed": "false"})
    bad_signature = create_job(
        client,
        files={"audio_file": ("piano.wav", b"not audio", "audio/wav")},
    )
    bad_mime = create_job(
        client,
        files={"audio_file": ("piano.wav", wav_bytes(), "video/mp4")},
    )
    bad_clip = create_job(client, data={"start_sec": "0", "end_sec": "0.5"})

    assert no_rights.status_code == 422
    assert bad_signature.json()["detail"]["code"] == "INVALID_SIGNATURE"
    assert bad_mime.json()["detail"]["code"] == "MIME_MISMATCH"
    assert bad_clip.json()["detail"]["code"] == "INVALID_CLIP"
    assert queue.calls == []


def test_create_rejects_file_over_25_mb(api_client) -> None:
    client, queue, storage_path = api_client
    oversized = b"RIFF" + b"\x00" * (25 * 1024 * 1024)

    response = create_job(
        client,
        files={"audio_file": ("huge.wav", oversized, "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"
    assert queue.calls == []
    assert list(storage_path.rglob("*")) == []


def test_create_accepts_real_mp3_and_m4a(api_client, tmp_path: Path) -> None:
    client, queue, _storage_path = api_client
    source = tmp_path / "source.wav"
    source.write_bytes(wav_bytes())

    for extension, codec, mime_type in [
        ("mp3", "libmp3lame", "audio/mpeg"),
        ("m4a", "aac", "audio/mp4"),
    ]:
        output = tmp_path / f"piano.{extension}"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-c:a",
                codec,
                "-y",
                str(output),
            ],
            check=True,
        )
        response = create_job(
            client,
            files={"audio_file": (output.name, output.read_bytes(), mime_type)},
        )
        assert response.status_code == 201

    assert len(queue.calls) == 2


def test_create_rejects_m4a_with_video_track(api_client, tmp_path: Path) -> None:
    client, queue, _storage_path = api_client
    source = tmp_path / "source.wav"
    output = tmp_path / "video.m4a"
    source.write_bytes(wav_bytes())
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=32x32:d=2",
            "-i",
            str(source),
            "-shortest",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-f",
            "mp4",
            "-y",
            str(output),
        ],
        check=True,
    )

    response = create_job(
        client,
        files={"audio_file": (output.name, output.read_bytes(), "audio/mp4")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "VIDEO_NOT_ALLOWED"
    assert queue.calls == []


def test_queue_failure_removes_database_row_and_object(api_client) -> None:
    client, queue, storage_path = api_client
    queue.error = ConnectionError("redis offline")

    response = create_job(client)

    assert response.status_code == 503
    factory = client.app.state.session_factory
    with factory() as session:
        assert session.scalar(select(TranscriptionJob)) is None
    assert not any(path.is_file() for path in storage_path.rglob("*"))


def test_retry_only_failed_jobs_and_stops_after_two_retries(api_client) -> None:
    client, queue, _storage_path = api_client
    job_id = create_job(client).json()["id"]

    assert client.post(f"/jobs/{job_id}/retry").status_code == 409

    mark_failed(client, job_id, 1)
    first_retry = client.post(f"/jobs/{job_id}/retry")
    assert first_retry.status_code == 200
    assert first_retry.json()["attempt_count"] == 2

    mark_failed(client, job_id, 2)
    second_retry = client.post(f"/jobs/{job_id}/retry")
    assert second_retry.status_code == 200
    assert second_retry.json()["attempt_count"] == 3

    mark_failed(client, job_id, 3)
    blocked = client.post(f"/jobs/{job_id}/retry")
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "Retry limit reached"
    assert queue.calls == [(job_id, 1), (job_id, 2), (job_id, 3)]


def test_delete_removes_source_artifact_and_database_row(api_client) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    crash_temp = client.app.state.settings.temp_path / f"pipeline-{job_id[:8]}-hardcrash"
    crash_temp.mkdir(parents=True)
    (crash_temp / "source.wav").write_bytes(b"private intermediate audio")
    artifact_path = storage_path / f"jobs/{job_id}/preview.mid"
    artifact_path.write_bytes(b"MThd")
    factory = client.app.state.session_factory
    with factory() as session:
        session.add(
            Artifact(
                id="artifact-id",
                job_id=job_id,
                type="midi",
                storage_key=f"jobs/{job_id}/preview.mid",
                size_bytes=4,
            )
        )
        session.commit()

    response = client.delete(f"/jobs/{job_id}")

    assert response.status_code == 204
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert not any(path.is_file() for path in storage_path.rglob("*"))
    assert not crash_temp.exists()
    with factory() as session:
        assert session.get(TranscriptionJob, job_id) is None


def test_delete_failure_is_structured_and_can_be_retried(api_client) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    artifact_path = storage_path / f"jobs/{job_id}/preview.mid"
    artifact_path.write_bytes(b"MThd")
    factory = client.app.state.session_factory
    with factory() as session:
        session.add(
            Artifact(
                id="retry-delete-artifact",
                job_id=job_id,
                type="midi",
                storage_key=f"jobs/{job_id}/preview.mid",
                size_bytes=4,
            )
        )
        session.commit()

    client.app.state.storage = FailingSecondDeleteStorage(client.app.state.storage)
    first_delete = client.delete(f"/jobs/{job_id}")

    assert first_delete.status_code == 503
    assert first_delete.json()["detail"] == "Task deletion is incomplete"
    assert not (storage_path / f"jobs/{job_id}/source.wav").exists()
    assert artifact_path.exists()
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        assert job.error_code == "DELETE_FAILED"
    assert client.post(f"/jobs/{job_id}/retry").status_code == 409

    second_delete = client.delete(f"/jobs/{job_id}")
    assert second_delete.status_code == 204
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert not artifact_path.exists()


def test_unknown_job_has_uniform_unavailable_response(api_client) -> None:
    client, _queue, _storage_path = api_client

    for method, path in [
        (client.get, "/jobs/missing"),
        (client.post, "/jobs/missing/retry"),
        (client.delete, "/jobs/missing"),
    ]:
        response = method(path)
        assert response.status_code == 404
        assert response.json()["detail"] == "Task unavailable"
