import json
from pathlib import Path

import pytest

from app.pipeline.harmonics import HarmonicEvidence, HarmonicRemoval, NoteOnsetEvidence
from app.pipeline.notation_context import NotationContext
from app.pipeline.score import _select_eighth_note_slots, build_score
from app.pipeline.transcribe import NoteEvent
from scripts.generate_regression_set import key_change
from scripts.run_structure_review import _notation_context_for_case


def test_key_change_uses_three_four_single_staff_and_one_note_per_slot():
    manifest_path = Path(__file__).parent / "fixtures/audio/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    case = next(item for item in manifest["cases"] if item["id"] == "13-key-change")
    assert case["texture_hint"] == "six_note_melody"
    events = [
        NoteEvent(index * 0.5, index * 0.5 + 0.42, pitch, 80, 0.8)
        for index, pitch in enumerate([60, 64, 67, 72, 67, 64] * 2)
    ]
    context = _notation_context_for_case(case)
    assert context is not None
    assert context.quantization_source == "expert_review"
    scored = build_score(
        events,
        notation_context=context,
    )
    ordered = sorted(scored.notation_notes, key=lambda event: event.start_sec)
    assert scored.analysis.time_signature == "3/4"
    assert scored.reconstruction["staff_layout"]["value"] == "single_treble"
    assert [event.pitch for event in ordered] == [60, 64, 67, 72, 67, 64] * 2
    assert [event.start_sec for event in ordered] == pytest.approx(
        [index * 0.5 for index in range(12)]
    )
    assert all(event.end_sec - event.start_sec <= 0.5 for event in ordered)
    assert scored.reconstruction["chord_count"] == 0
    assert scored.reconstruction["voice_count"] == 0
    assert scored.reconstruction["melody_cleanup"]["status"] == "evidence_unavailable"
    assert scored.reconstruction["six_note_melody_cleanup"]["selected_count"] == 12


def test_second_segment_prefers_transposed_independent_attack_over_original_tail():
    events = [
        NoteEvent(14.5, 14.92, 64, 85, 0.8),
        NoteEvent(15.0, 15.42, 60, 75, 0.75),
        NoteEvent(15.0, 15.42, 62, 85, 0.8),
    ]
    evidence = HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=(
            NoteOnsetEvidence(64, 14.5, 14.92, 3.0, True),
            NoteOnsetEvidence(60, 15.0, 15.42, 0.7, False),
            NoteOnsetEvidence(62, 15.0, 15.42, 3.0, True),
        ),
    )
    context = _notation_context_for_case({"texture_hint": "six_note_melody"})
    assert context is not None

    scored = build_score(events, harmonic_evidence=evidence, notation_context=context)

    assert [(event.start_sec, event.pitch) for event in scored.notation_notes] == [
        (14.5, 64),
        (15.0, 62),
    ]
    cleanup = scored.reconstruction["six_note_melody_cleanup"]
    assert cleanup["non_independent_rejected_count"] == 1
    assert cleanup["ambiguous_slot_count"] == 0


def test_two_independent_attacks_remain_ambiguous_instead_of_silent_deletion():
    events = [
        NoteEvent(0.0, 0.42, 60, 80, 0.8),
        NoteEvent(0.0, 0.42, 72, 70, 0.7),
    ]
    evidence = HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=(
            NoteOnsetEvidence(60, 0.0, 0.42, 3.0, True),
            NoteOnsetEvidence(72, 0.0, 0.42, 3.0, True),
        ),
    )

    selected, audit = _select_eighth_note_slots(
        events, quarter_seconds=1.0, harmonic_evidence=evidence
    )

    assert selected == events
    assert audit["status"] == "ambiguous"
    assert audit["ambiguous_slot_count"] == 1
    assert audit["dropped_count"] == 0
    assert audit["removals"] == []


def test_key_change_generator_has_six_eighth_slots_per_measure_and_no_overlap():
    notes = key_change()

    assert len(notes) == 60
    assert [note.start for note in notes] == pytest.approx(
        [index * 0.5 for index in range(60)]
    )
    assert [note.pitch for note in notes[:6]] == [60, 64, 67, 72, 67, 64]
    assert [note.pitch for note in notes[30:36]] == [62, 66, 69, 74, 69, 66]
    assert max(note.end for note in notes[:30]) <= 15.0
    assert min(note.start for note in notes[30:]) == 15.0


def test_six_note_slots_reject_audio_proven_harmonics():
    fundamentals = [60, 64, 67, 72, 67, 64]
    events = []
    removals = []
    for index, pitch in enumerate(fundamentals):
        start = index * 0.5
        fundamental = NoteEvent(start, start + 0.42, pitch, 70, 0.7)
        harmonic = NoteEvent(start, start + 0.42, pitch + 12, 95, 0.95)
        events.extend((fundamental, harmonic))
        removals.append(
            HarmonicRemoval(
                fundamental_pitch=pitch,
                harmonic_pitch=pitch + 12,
                harmonic_start_sec=start,
                harmonic_end_sec=start + 0.42,
                harmonic_number=2,
                tuning_error_cents=0.0,
                energy_ratio=0.1,
                independent_onset=False,
            )
        )
    evidence = HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=tuple(removals),
    )
    scored = build_score(
        events,
        harmonic_evidence=evidence,
        notation_context=NotationContext(
            texture_hint="six_note_melody",
            time_signature="3/4",
            time_signature_source="expert_review",
            time_signature_confidence=1.0,
            quantization_divisions_per_quarter=4,
            quantization_source="expert_review",
            tempo_bpm=60,
            tempo_source="expert_review",
            melody_pitch_pattern=tuple(fundamentals),
            melody_pattern_source="expert_review",
        ),
    )

    ordered = sorted(scored.notation_notes, key=lambda event: event.start_sec)
    assert [event.pitch for event in ordered] == fundamentals
    assert scored.reconstruction["six_note_melody_cleanup"]["harmonic_rejected_count"] == 6
    assert scored.reconstruction["chord_count"] == 0
    assert scored.reconstruction["voice_count"] == 0
