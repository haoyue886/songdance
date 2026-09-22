"""Contract tests for the teacher-reviewed 12-compound-68 fixture.

These tests deliberately keep the fixture scoped to the compound-68 context.  They
do not change the legacy ``compound_68`` synthesis or any other regression case.
"""

import json
from pathlib import Path

import pytest

from app.pipeline.artifacts import write_timeline
from app.pipeline.notation_context import NotationContext
from app.pipeline.score import _apply_compound_68_constraints, build_score
from app.pipeline.transcribe import NoteEvent

FIXTURE_ROOT = Path(__file__).parent / "fixtures/audio"


def _compound_context() -> NotationContext:
    return NotationContext(
        texture_hint="compound_68",
        time_signature="6/8",
        time_signature_source="expert_review",
        time_signature_confidence=1.0,
        quantization_divisions_per_quarter=4,
        quantization_source="expert_review",
        tempo_bpm=120,
        tempo_source="expert_review",
    )


def test_compound_68_manifest_records_teacher_contract() -> None:
    manifest = json.loads(
        (FIXTURE_ROOT / "compound-68-expert-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["case_id"] == "12-compound-68"
    assert manifest["time_signature"] == "6/8"
    assert manifest["treble_pattern"] == ["do", "mi", "sol", "la", "sol", "mi"]
    assert manifest["treble_note_value"] == "eighth"
    assert manifest["first_note_value"] == "dotted_eighth_or_tie"
    assert manifest["bass"]["status"] == "suspicious_noise_layer"
    assert manifest["acceptance"] == {
        "first_note_longer_than_other_five": True,
        "reject_unrelated_low_frequency_events": True,
        "preserve_suspicious_events_in_audit": True,
    }


def test_compound_constraints_lengthen_each_measure_downbeat_and_audit_low_noise() -> None:
    # Two six-eighth-note treble measures plus one unrelated low-frequency event.
    events = [
        NoteEvent(0.00, 0.20, 60, 84, 0.9),
        NoteEvent(0.25, 0.45, 64, 84, 0.9),
        NoteEvent(0.50, 0.70, 67, 84, 0.9),
        NoteEvent(0.75, 0.95, 69, 84, 0.9),
        NoteEvent(1.00, 1.20, 67, 84, 0.9),
        NoteEvent(1.25, 1.45, 64, 84, 0.9),
        NoteEvent(1.50, 1.70, 60, 84, 0.9),
        NoteEvent(1.75, 1.95, 64, 84, 0.9),
        NoteEvent(2.00, 2.20, 67, 84, 0.9),
        NoteEvent(2.25, 2.45, 69, 84, 0.9),
        NoteEvent(2.50, 2.70, 67, 84, 0.9),
        NoteEvent(2.75, 2.95, 64, 84, 0.9),
        NoteEvent(0.10, 0.30, 36, 55, 0.7),
    ]

    constrained, audit = _apply_compound_68_constraints(
        events, quarter_seconds=0.5, time_signature="6/8"
    )

    assert any(event.pitch == 36 for event in constrained)
    assert audit["removed_suspicious_low_frequency_count"] == 0
    assert audit["preserved_low_frequency_count"] == 1
    assert audit["audit_reason"] == "INSUFFICIENT_EVENT_LEVEL_EVIDENCE_PRESERVE"
    assert audit["first_note_duration_rule"] == "dotted_eighth"

    first_measure_downbeat = next(event for event in constrained if event.start_sec == 0)
    second_measure_downbeat = next(event for event in constrained if event.start_sec == 1.5)
    assert first_measure_downbeat.end_sec - first_measure_downbeat.start_sec == pytest.approx(0.375)
    assert second_measure_downbeat.end_sec - second_measure_downbeat.start_sec == pytest.approx(
        0.375
    )
    assert audit["accented_first_note_count"] == 2


def test_compound_constraints_are_exposed_in_timeline_audit(tmp_path: Path) -> None:
    events = [
        NoteEvent(0.00, 0.20, 60, 84, 0.9),
        NoteEvent(0.25, 0.45, 64, 84, 0.9),
        NoteEvent(0.50, 0.70, 67, 84, 0.9),
        NoteEvent(0.75, 0.95, 69, 84, 0.9),
        NoteEvent(1.00, 1.20, 67, 84, 0.9),
        NoteEvent(1.25, 1.45, 64, 84, 0.9),
        NoteEvent(0.10, 0.30, 36, 55, 0.7),
    ]
    scored = build_score(events, title="12-compound-68", notation_context=_compound_context())
    destination = tmp_path / "timeline.json"
    write_timeline(scored, destination)
    timeline = json.loads(destination.read_text(encoding="utf-8"))

    cleanup = timeline["reconstruction"]["compound_68_cleanup"]
    assert timeline["time_signature"] == "6/8"
    assert cleanup["status"] == "applied"
    assert cleanup["removed_suspicious_low_frequency_count"] == 0
    assert cleanup["preserved_low_frequency_count"] == 1
    assert cleanup["audit_reason"] == "INSUFFICIENT_EVENT_LEVEL_EVIDENCE_PRESERVE"
    assert cleanup["first_note_duration_rule"] == "dotted_eighth"
    assert all(note["pitch"] >= 48 for note in timeline["notation_notes"])
