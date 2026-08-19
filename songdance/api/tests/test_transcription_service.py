import json
from pathlib import Path

import pretty_midi
import pytest
from music21 import converter

from app.models import TranscriptionJob
from app.pipeline.errors import ModelInferenceError, ScoreGenerationError
from app.pipeline.transcribe import MODEL_VERSION
from app.services.transcription import run_transcription_job
from tests.conftest import wav_bytes
from tests.test_jobs import create_job
from tests.transcription_helpers import fake_transcription, run_service


def test_real_pipeline_creates_parseable_private_artifacts(api_client) -> None:
    client, _queue, storage_path = api_client
    created = create_job(
        client,
        files={
            "audio_file": (
                "a4.wav",
                wav_bytes(duration=2, sample_rate=22_050, frequency=440),
                "audio/wav",
            )
        },
    )
    job_id = created.json()["id"]

    run_service(client, job_id)

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert payload["stage"] == "completed"
    assert {item["type"] for item in payload["artifacts"]} == {
        "raw_midi",
        "raw_timeline",
        "midi",
        "musicxml",
        "timeline",
    }
    assert all(item["status"] == "succeeded" for item in payload["artifacts"])

    artifact_root = storage_path / f"jobs/{job_id}/artifacts/attempt-1"
    raw_midi = pretty_midi.PrettyMIDI(str(artifact_root / "raw.mid"))
    score_midi = pretty_midi.PrettyMIDI(str(artifact_root / "score.mid"))
    score = converter.parse(str(artifact_root / "score.musicxml"))
    assert sum(len(item.notes) for item in raw_midi.instruments) >= 1
    assert sum(len(item.notes) for item in score_midi.instruments) >= 1
    assert len(list(score.recurse().getElementsByClass("Measure"))) >= 1
    assert (artifact_root / "timeline.json").stat().st_size > 50
    assert (artifact_root / "raw-timeline.json").stat().st_size > 50
    assert payload["quality_report"] is not None

    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None and job.result is not None
        assert job.result.note_count and job.result.note_count >= 1
        assert job.result.model_version == MODEL_VERSION


def test_musicxml_failure_does_not_block_midi_and_retry_is_idempotent(
    api_client, monkeypatch
) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]

    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription_artifacts.write_musicxml",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("xml failed")),
    )

    run_service(client, job_id)
    run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    outcomes = {item["type"]: item for item in payload["artifacts"]}
    assert payload["status"] == "succeeded"
    assert len(outcomes) == 5
    assert outcomes["musicxml"]["status"] == "failed"
    assert outcomes["musicxml"]["error_code"] == "MUSICXML_GENERATION_FAILED"
    assert outcomes["midi"]["status"] == "succeeded"
    quality = json.loads(payload["quality_report"]["summary"])
    assert quality["musicxml_parse"] == {
        "status": "failed",
        "error_code": "MUSICXML_GENERATION_FAILED",
    }
    assert quality["structure_errors"] == ["MUSICXML_GENERATION_FAILED"]
    assert (storage_path / f"jobs/{job_id}/artifacts/attempt-1/score.mid").is_file()
    assert client.delete(f"/jobs/{job_id}").status_code == 204


def test_score_failure_preserves_raw_model_midi(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription.build_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ScoreGenerationError()),
    )

    run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    assert payload["status"] == "failed"
    assert payload["stage"] == "score"
    assert payload["error_code"] == "SCORE_GENERATION_FAILED"
    outcomes = {item["type"]: item for item in payload["artifacts"]}
    assert outcomes["raw_midi"]["status"] == "succeeded"
    assert outcomes["raw_midi"]["error_code"] is None
    assert {kind for kind, item in outcomes.items() if item["status"] == "failed"} == {
        "midi",
        "musicxml",
        "timeline",
    }
    assert all(
        outcomes[kind]["error_code"] == "SCORE_GENERATION_FAILED"
        for kind in ("midi", "musicxml", "timeline")
    )
    assert (storage_path / f"jobs/{job_id}/artifacts/attempt-1/raw.mid").is_file()
    quality = json.loads(payload["quality_report"]["summary"])
    assert quality["raw_note_count"] == 1
    assert quality["cleaned_note_count"] == 1
    assert quality["cleanup"]["status"] == "applied"
    assert quality["musicxml_parse"] == {
        "status": "failed",
        "error_code": "SCORE_GENERATION_FAILED",
    }


def test_stale_attempt_cannot_clear_or_publish_the_current_attempt(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    factory = client.app.state.session_factory
    storage = client.app.state.storage
    original_put = storage.put_file

    def promote_retry_after_stale_upload(key: str, source: Path, content_type: str) -> None:
        original_put(key, source, content_type)
        if key.endswith("attempt-1/raw.mid"):
            with factory() as session:
                job = session.get(TranscriptionJob, job_id)
                assert job is not None
                job.attempt_count = 2
                session.commit()

    monkeypatch.setattr(storage, "put_file", promote_retry_after_stale_upload)

    run_transcription_job(
        job_id,
        client.app.state.settings,
        factory,
        storage,
        attempt=1,
    )

    assert client.get(f"/jobs/{job_id}").json()["artifacts"] == []
    assert not any(path.is_file() for path in storage_path.rglob("attempt-1/*"))
    monkeypatch.setattr(storage, "put_file", original_put)

    run_transcription_job(
        job_id,
        client.app.state.settings,
        factory,
        storage,
        attempt=2,
    )

    payload = client.get(f"/jobs/{job_id}").json()
    assert payload["status"] == "succeeded"
    artifact_files = [
        path for path in (storage_path / f"jobs/{job_id}/artifacts").rglob("*") if path.is_file()
    ]
    assert artifact_files
    assert all("attempt-2" in path.parts for path in artifact_files)


def test_storage_failure_has_a_distinct_artifact_error(api_client, monkeypatch) -> None:
    client, _queue, _storage_path = api_client
    job_id = create_job(client).json()["id"]
    storage = client.app.state.storage
    original_put = storage.put_file

    def fail_musicxml(key: str, source: Path, content_type: str) -> None:
        if key.endswith("score.musicxml"):
            raise ConnectionError("storage unavailable")
        original_put(key, source, content_type)

    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(storage, "put_file", fail_musicxml)

    run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    outcomes = {item["type"]: item for item in payload["artifacts"]}
    assert payload["status"] == "succeeded"
    assert outcomes["musicxml"]["status"] == "failed"
    assert outcomes["musicxml"]["error_code"] == "MUSICXML_STORAGE_FAILED"
    assert outcomes["midi"]["status"] == "succeeded"
    quality = json.loads(payload["quality_report"]["summary"])
    assert quality["musicxml_parse"] == {
        "status": "failed",
        "error_code": "MUSICXML_STORAGE_FAILED",
    }
    assert quality["structure_errors"] == ["MUSICXML_STORAGE_FAILED"]


def test_critical_storage_failure_becomes_the_job_error(api_client, monkeypatch) -> None:
    client, _queue, _storage_path = api_client
    job_id = create_job(client).json()["id"]
    storage = client.app.state.storage
    original_put = storage.put_file

    def fail_midi(key: str, source: Path, content_type: str) -> None:
        if key.endswith("score.mid"):
            raise ConnectionError("storage unavailable")
        original_put(key, source, content_type)

    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(storage, "put_file", fail_midi)

    run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "MIDI_STORAGE_FAILED"
    assert {item["type"]: item["error_code"] for item in payload["artifacts"]}["midi"] == (
        "MIDI_STORAGE_FAILED"
    )


def test_retry_cleanup_hides_stale_artifacts_before_storage_deletion(
    api_client, monkeypatch
) -> None:
    client, _queue, _storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_service(client, job_id)
    assert len(client.get(f"/jobs/{job_id}").json()["artifacts"]) == 5

    storage = client.app.state.storage
    original_delete = storage.delete
    calls = 0

    def interrupt_delete(key: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ConnectionError("storage unavailable")
        original_delete(key)

    monkeypatch.setattr(storage, "delete", interrupt_delete)
    with pytest.raises(ConnectionError):
        run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    assert payload["artifacts"] == []
    factory = client.app.state.session_factory
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None and job.result is None

    monkeypatch.setattr(storage, "delete", original_delete)
    run_service(client, job_id)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "succeeded"


def test_model_failure_updates_job_with_structured_error(api_client, monkeypatch) -> None:
    client, _queue, _storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
        lambda _path, **_kwargs: (_ for _ in ()).throw(ModelInferenceError()),
    )

    run_service(client, job_id)

    payload = client.get(f"/jobs/{job_id}").json()
    assert payload["status"] == "failed"
    assert payload["stage"] == "transcribing"
    assert payload["error_code"] == "MODEL_INFERENCE_FAILED"
