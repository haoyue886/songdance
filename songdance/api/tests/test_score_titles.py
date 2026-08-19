import pytest

from app.models import TranscriptionJob
from app.services.transcription_source import score_title
from tests.conftest import wav_bytes
from tests.test_jobs import create_job
from tests.transcription_helpers import fake_transcription, run_service


def test_uploaded_filename_becomes_the_only_visible_score_title(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _queue, storage_path = api_client
    created = create_job(
        client,
        files={"audio_file": ("my-piano.take.wav", wav_bytes(), "audio/wav")},
    )
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, created.json()["id"])
        assert job is not None
        assert job.source_asset.original_filename == "my-piano.take.wav"
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)

    run_service(client, created.json()["id"])

    score_path = storage_path / f"jobs/{created.json()['id']}/artifacts/attempt-1/score.musicxml"
    document = score_path.read_text(encoding="utf-8")
    assert "<work-title>" not in document
    assert "<movement-title>my-piano.take</movement-title>" in document
    assert '<creator type="composer">Music21</creator>' not in document
    assert "music21 v.10.5.0" in document


def test_legacy_job_without_filename_uses_fallback_score_title(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _queue, storage_path = api_client
    created = create_job(client)
    job_id = created.json()["id"]
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.source_asset.original_filename = None
        session.commit()
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)

    run_service(client, job_id)

    score_path = storage_path / f"jobs/{job_id}/artifacts/attempt-1/score.musicxml"
    document = score_path.read_text(encoding="utf-8")
    assert "<movement-title>SongDance Transcription</movement-title>" in document


def test_extension_only_filename_completes_with_fallback_score_title(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _queue, storage_path = api_client
    created = create_job(
        client,
        files={"audio_file": (".wav", wav_bytes(), "audio/wav")},
    )
    assert created.status_code == 201
    job_id = created.json()["id"]
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        assert job.source_asset.original_filename == ".wav"
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)

    run_service(client, job_id)

    score_path = storage_path / f"jobs/{job_id}/artifacts/attempt-1/score.musicxml"
    document = score_path.read_text(encoding="utf-8")
    assert "<movement-title>SongDance Transcription</movement-title>" in document


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("piece.wav", "piece"),
        ("archive.take.m4a", "archive.take"),
        (".wav", "SongDance Transcription"),
        (" .wav", "SongDance Transcription"),
        (None, "SongDance Transcription"),
    ],
)
def test_score_title_uses_filename_stem_with_legacy_fallback(
    filename: str | None, expected: str
) -> None:
    assert score_title(filename) == expected
