import json
from pathlib import Path

import pytest

from app.pipeline.cleanup import (
    ADJACENT_SAME_PITCH_PRESERVED,
    DUPLICATE_NOTE_REMOVED,
    EXCESSIVE_DURATION_CLIPPED,
    HARMONIC_CANDIDATE_REMOVED,
    LOW_CONFIDENCE_REMOVED,
    NOTE_PRESERVED,
    OVERLAPPING_SAME_PITCH_PRESERVED,
    SHORT_NOTE_REMOVED,
    CleanupConfig,
    clean_note_events,
)
from app.pipeline.errors import NoteCleanupError
from app.pipeline.transcribe import NoteEvent
from app.services.transcription import run_transcription_job
from tests.test_jobs import create_job
from tests.test_transcription_service import fake_transcription


def test_cleanup_filters_low_confidence_and_short_notes_with_reasons() -> None:
    events = [
        NoteEvent(0, 0.5, 60, 90, 0.9),
        NoteEvent(0.6, 1.0, 62, 80, 0.09),
        NoteEvent(1.1, 1.12, 64, 70, 0.8),
    ]

    result = clean_note_events(events)

    assert result.events == [events[0]]
    assert result.summary()["reason_counts"] == {
        LOW_CONFIDENCE_REMOVED: 1,
        SHORT_NOTE_REMOVED: 1,
        DUPLICATE_NOTE_REMOVED: 0,
        EXCESSIVE_DURATION_CLIPPED: 0,
        NOTE_PRESERVED: 1,
        ADJACENT_SAME_PITCH_PRESERVED: 0,
        OVERLAPPING_SAME_PITCH_PRESERVED: 0,
        HARMONIC_CANDIDATE_REMOVED: 0,
    }
    assert result.summary()["removed_note_count"] == 2


def test_cleanup_keeps_best_duplicate_and_preserves_distinct_onsets() -> None:
    events = [
        NoteEvent(0.0, 0.5, 60, 80, 0.7),
        NoteEvent(0.0, 0.6, 60, 90, 0.9),
        NoteEvent(0.005, 0.65, 60, 85, 0.85),
        NoteEvent(0.02, 0.7, 60, 100, 0.8),
    ]

    result = clean_note_events(
        events, CleanupConfig(adjacent_same_pitch_gap_seconds=0)
    )

    assert result.events == [events[1], events[2], events[3]]
    assert result.reason_counts[DUPLICATE_NOTE_REMOVED] == 1


def test_cleanup_preserves_adjacent_same_pitch_fragments_with_a_reason() -> None:
    events = [
        NoteEvent(0, 0.08, 60, 80, 0.7, "left"),
        NoteEvent(0.1, 0.18, 60, 90, 0.9, "left"),
        NoteEvent(0.1, 0.18, 64, 90, 0.9, "right"),
    ]

    result = clean_note_events(events)

    assert result.events == events
    assert result.reason_counts[ADJACENT_SAME_PITCH_PRESERVED] == 1
    assert result.summary()["merged_note_count"] == 0


def test_cleanup_is_stable_for_reversed_input() -> None:
    events = [
        NoteEvent(0.52, 1.0, 60, 90, 0.9),
        NoteEvent(0, 0.5, 60, 80, 0.7),
        NoteEvent(0, 0.5, 64, 80, 0.8),
    ]

    assert clean_note_events(events).summary() == clean_note_events(
        list(reversed(events))
    ).summary()
    assert clean_note_events(events).events == clean_note_events(list(reversed(events))).events


def test_cleanup_does_not_merge_normal_repeated_notes() -> None:
    events = [
        NoteEvent(0, 0.5, 60, 80, 0.8),
        NoteEvent(0.5, 1.0, 60, 80, 0.8),
    ]

    result = clean_note_events(events)

    assert result.events == events
    assert result.reason_counts[ADJACENT_SAME_PITCH_PRESERVED] == 1


def test_cleanup_clips_excessive_sustain_and_explains_preserved_overlap() -> None:
    events = [
        NoteEvent(0, 40, 60, 80, 0.8),
        NoteEvent(0.5, 1.5, 60, 90, 0.9),
    ]

    result = clean_note_events(events)

    assert result.events == [
        NoteEvent(0, 30, 60, 80, 0.8),
        events[1],
    ]
    assert result.reason_counts[EXCESSIVE_DURATION_CLIPPED] == 1
    assert result.reason_counts[OVERLAPPING_SAME_PITCH_PRESERVED] == 1


def test_cleanup_rejects_invalid_events_and_empty_output() -> None:
    with pytest.raises(NoteCleanupError, match="无效数值"):
        clean_note_events([NoteEvent(0, float("nan"), 60, 90, 0.9)])
    with pytest.raises(NoteCleanupError, match="移除了全部"):
        clean_note_events([NoteEvent(0, 0.01, 60, 90, 0.9)])


def test_service_applies_cleanup_and_keeps_raw_timeline(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    raw_events = [
        NoteEvent(0, 0.5, 60, 80, 0.8),
        NoteEvent(0, 0.6, 60, 90, 0.9),
        NoteEvent(0.8, 0.82, 64, 70, 0.8),
    ]
    _events, midi = fake_transcription(Path("unused"))
    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
        lambda *_args, **_kwargs: (raw_events, midi),
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    payload = client.get(f"/jobs/{job_id}").json()
    report = json.loads(payload["quality_report"]["summary"])
    artifact_root = storage_path / f"jobs/{job_id}/artifacts/attempt-1"
    raw_timeline = json.loads((artifact_root / "raw-timeline.json").read_text())
    timeline = json.loads((artifact_root / "timeline.json").read_text())
    assert len(raw_timeline["notes"]) == 3
    assert report["cleanup"]["reason_counts"][DUPLICATE_NOTE_REMOVED] == 1
    assert report["cleanup"]["reason_counts"][SHORT_NOTE_REMOVED] == 1
    assert report["cleaned_note_count"] == 1
    assert timeline["kind"] == "cleaned_note_events"
    assert timeline["cleanup"]["output_note_count"] == 1


def test_service_falls_back_to_raw_events_when_cleanup_fails(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription.clean_note_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(NoteCleanupError()),
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    payload = client.get(f"/jobs/{job_id}").json()
    report = json.loads(payload["quality_report"]["summary"])
    timeline = json.loads(
        (
            storage_path / f"jobs/{job_id}/artifacts/attempt-1/timeline.json"
        ).read_text()
    )
    assert payload["status"] == "succeeded"
    assert report["cleanup"]["status"] == "failed"
    assert report["cleanup"]["fallback_used"] is True
    assert report["raw_note_count"] == report["cleaned_note_count"] == 1
    assert "NOTE_CLEANUP_FALLBACK" in timeline["quality_flags"]


def test_service_falls_back_to_raw_events_on_unexpected_cleanup_error(
    api_client, monkeypatch
) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription.clean_note_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("cleanup bug")),
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    payload = client.get(f"/jobs/{job_id}").json()
    report = json.loads(payload["quality_report"]["summary"])
    timeline = json.loads(
        (
            storage_path / f"jobs/{job_id}/artifacts/attempt-1/timeline.json"
        ).read_text()
    )
    assert payload["status"] == "succeeded"
    assert report["cleanup"]["status"] == "failed"
    assert report["cleanup"]["error_code"] == "NOTE_CLEANUP_UNEXPECTED_ERROR"
    assert report["raw_note_count"] == report["cleaned_note_count"] == 1
    assert "NOTE_CLEANUP_FALLBACK" in timeline["quality_flags"]
