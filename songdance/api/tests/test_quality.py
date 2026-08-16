import json

from app.pipeline.quality import build_quality_report
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent


def test_quality_report_is_stable_and_keeps_raw_and_cleaned_counts() -> None:
    raw = [
        NoteEvent(0, 1, 60, 100, 0.9),
        NoteEvent(0, 1, 60, 100, 0.8, "left"),
        NoteEvent(0.5, 1.5, 64, 80, 0.7),
    ]
    report = build_quality_report(raw, build_score(raw))

    assert report == build_quality_report(list(reversed(raw)), build_score(list(reversed(raw))))
    assert report["raw_note_count"] == 3
    assert report["cleaned_note_count"] == 3
    assert report["duplicate_event_count"] == 1
    assert report["confidence"] == {"min": 0.7, "max": 0.9, "mean": 0.8}
    assert report["model"] == {"version": "not_recorded", "thresholds": {}}
    assert report["note_metrics"]["status"] == "not_evaluated"
    assert report["note_metrics"]["precision"] is None
    assert report["human_rating"] == {"status": "not_evaluated", "rating": None}
    assert set(report["dependencies"]) == {
        "basic-pitch",
        "librosa",
        "mir-eval",
        "music21",
        "pretty_midi",
    }
    assert len(str(report["raw_event_fingerprint"])) == 64
    assert report["musicxml_parse"] == {"status": "passed"}
    assert report["structure_errors"] == []
    assert report["structure"]["part_count"] == 2
    assert report["structure"]["measure_duration_error_count"] == 0
    assert report["structure"]["short_rest_count"] == 0
    assert report["structure"]["key_signature_status"] == "detected"
    assert report["reconstruction"]["status"] in {"reconstructed", "fallback"}
    assert report["reconstruction"]["voicing"]["version"].startswith("voicing-v2/")


def test_quality_report_evaluates_reference_metrics_and_sorts_distinct_events() -> None:
    reference = [
        NoteEvent(0, 1, 60, 100, 1.0),
        NoteEvent(1, 2, 64, 100, 1.0),
    ]
    estimated = [
        NoteEvent(1.03, 2, 64, 100, 0.2, "right"),
        NoteEvent(0.02, 1, 60, 100, 0.9, "left"),
    ]
    report = build_quality_report(
        estimated,
        build_score(estimated),
        reference_events=reference,
        human_rating="minor_edits",
        model_version="fixture-model",
        thresholds={"frame": 0.3, "onset": 0.5},
    )

    assert report["model"] == {
        "version": "fixture-model",
        "thresholds": {"frame": 0.3, "onset": 0.5},
    }
    assert report["note_metrics"] == {
        "status": "evaluated",
        "reference_note_count": 2,
        "estimated_note_count": 2,
        "matched_note_count": 2,
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "overlap": 0.975,
        "mean_onset_error_ms": 25.0,
        "mean_pitch_error_semitones": 0.0,
    }
    assert report["human_rating"] == {"status": "evaluated", "rating": "minor_edits"}

    reversed_events = list(reversed(estimated))
    assert report == build_quality_report(
        reversed_events,
        build_score(reversed_events),
        reference_events=reference,
        human_rating="minor_edits",
        model_version="fixture-model",
        thresholds={"onset": 0.5, "frame": 0.3},
    )


def test_job_response_exposes_serialized_quality_report(api_client, monkeypatch) -> None:
    from pathlib import Path

    import pretty_midi

    from app.pipeline.transcribe import NoteEvent
    from app.services.transcription import run_transcription_job
    from tests.test_jobs import create_job

    def fake_transcription(_audio_path: Path, **_kwargs):
        midi = pretty_midi.PrettyMIDI(initial_tempo=120)
        piano = pretty_midi.Instrument(program=0)
        piano.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0, end=1))
        midi.instruments.append(piano)
        return [NoteEvent(0, 1, 60, 100, 0.9)], midi

    client, _queue, _storage = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    report = client.get(f"/jobs/{job_id}").json()["quality_report"]
    assert report is not None
    assert json.loads(report["summary"])["raw_note_count"] == 1
