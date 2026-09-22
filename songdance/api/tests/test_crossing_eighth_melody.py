import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pretty_midi
import pytest
from music21 import chord, converter, note

from app.pipeline.analysis import AnalysisConfig, fallback_analysis
from app.pipeline.artifacts import write_timeline
from app.pipeline.crossing_eighth import select_crossing_eighth_events
from app.pipeline.harmonics import HarmonicEvidence, HarmonicRemoval, NoteOnsetEvidence
from app.pipeline.notation_context import NotationContext
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.transcribe import NoteEvent
from scripts.run_structure_review import _notation_context_for_case

RIGHT = (72, 69, 66, 63, 60, 57, 54, 51)
LEFT = (48, 51, 54, 57, 60, 63, 66, 69)


def _crossing_context() -> NotationContext:
    context = _notation_context_for_case(
        {"texture_hint": "crossing_eighth_melody"}
    )
    assert context is not None
    return context


def _source_cycle_events(cycles: int = 1, start_sec: float = 0.0) -> list[NoteEvent]:
    events: list[NoteEvent] = []
    for cycle in range(cycles):
        for index, (right, left) in enumerate(zip(RIGHT, LEFT, strict=True)):
            onset = start_sec + (cycle * 8 + index) * 0.5
            events.append(NoteEvent(onset, onset + 0.42, right, 88, 0.9))
            events.append(NoteEvent(onset, onset + 0.65, left, 78, 0.8))
    return events


def test_manifest_records_crossing_texture_hint() -> None:
    manifest = json.loads(
        (Path(__file__).parent / "fixtures/audio/manifest.json").read_text()
    )
    case = next(item for item in manifest["cases"] if item["id"] == "14-hand-crossing")
    assert case["texture_hint"] == "crossing_eighth_melody"
    context = _crossing_context()
    assert context.time_signature == "4/4"
    assert context.tempo_bpm == 60
    assert context.quantization_divisions_per_quarter == 4


def test_crossing_context_keeps_both_hands_and_uniform_eighths() -> None:
    scored = build_score(_source_cycle_events(), notation_context=_crossing_context())
    notes = sorted(scored.notation_notes, key=lambda item: (item.start_sec, item.pitch))
    assert scored.analysis.time_signature == "4/4"
    assert scored.tempo_bpm == 60
    assert scored.reconstruction["staff_layout"]["value"] == "grand_staff"
    assert [(item.start_sec, item.pitch) for item in notes] == sorted(
        (index * 0.5, pitch)
        for index, pair in enumerate(zip(LEFT, RIGHT, strict=True))
        for pitch in pair
    )
    assert all(abs(item.end_sec - item.start_sec - 0.5) < 1e-6 for item in notes)
    crossing_c4 = [
        item for item in notes if item.start_sec == pytest.approx(2.0) and item.pitch == 60
    ]
    assert len(crossing_c4) == 2
    cleanup = scored.reconstruction["crossing_eighth_cleanup"]
    assert cleanup["duration_rule"] == "uniform_eighth_note"
    assert cleanup["selected_count"] == 16
    score_notes = list(scored.score.recurse().notes)
    assert score_notes
    assert all(float(item.quarterLength) == 0.5 for item in score_notes)
    assert any(isinstance(item, (note.Note, chord.Chord)) for item in score_notes)


def test_helper_does_not_rewrite_unmatched_pitches_or_invent_missing_notes() -> None:
    events = [
        NoteEvent(0.0, 0.9, 60, 88, 0.9),
        NoteEvent(0.0, 0.9, 57, 78, 0.8),
        NoteEvent(0.5, 1.4, 63, 88, 0.9),
    ]
    selected, audit = select_crossing_eighth_events(events, quarter_seconds=1.0)
    assert [(item.start_sec, item.pitch) for item in selected] == [
        (0.0, 57),
        (0.0, 60),
        (0.5, 63),
    ]
    assert all(abs(item.end_sec - item.start_sec - 0.5) < 1e-6 for item in selected)
    assert audit["selected_count"] == 3
    assert audit["dropped_count"] == 0


def test_late_start_anchors_to_absolute_eighth_grid() -> None:
    selected, audit = select_crossing_eighth_events(
        _source_cycle_events(start_sec=2.0)[:4],
        quarter_seconds=1.0,
    )
    assert [item.start_sec for item in selected] == [2.0, 2.0, 2.5, 2.5]
    assert audit["origin_seconds"] == 0.0
    assert all(abs(item.end_sec - item.start_sec - 0.5) < 1e-6 for item in selected)


def test_empty_events_are_a_no_op() -> None:
    selected, audit = select_crossing_eighth_events([], quarter_seconds=1.0)
    assert selected == []
    assert audit["status"] == "no_events"


def test_crossing_requires_explicit_context_and_never_runs_for_default_uploads(monkeypatch):
    with pytest.raises(ValueError, match="crossing notation requires"):
        NotationContext(texture_hint="crossing_eighth_melody")

    def forbidden(*args, **kwargs):
        raise AssertionError("crossing logic used outside reviewed context")

    monkeypatch.setattr("app.pipeline.score.select_crossing_eighth_events", forbidden)
    scored = build_score(_source_cycle_events())
    assert scored.tempo_bpm == 120
    assert scored.reconstruction["crossing_eighth_cleanup"] == {"status": "not_applied"}


def test_proven_harmonics_are_removed_and_ambiguous_extras_remain() -> None:
    events = [
        NoteEvent(0.0, 0.42, 48, 78, 0.8),
        NoteEvent(0.0, 0.42, 72, 88, 0.9),
        NoteEvent(0.0, 0.42, 84, 40, 0.4),
        NoteEvent(0.5, 0.92, 51, 78, 0.8),
        NoteEvent(0.5, 0.92, 69, 88, 0.9),
        NoteEvent(0.5, 0.92, 81, 42, 0.35),
    ]
    evidence = HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(
            HarmonicRemoval(
                fundamental_pitch=72,
                harmonic_pitch=84,
                harmonic_start_sec=0.0,
                harmonic_end_sec=0.42,
                harmonic_number=2,
                tuning_error_cents=0.0,
                energy_ratio=0.1,
                independent_onset=False,
            ),
        ),
        onset_observations=(
            NoteOnsetEvidence(48, 0.0, 0.42, 3.0, True),
            NoteOnsetEvidence(72, 0.0, 0.42, 3.0, True),
            NoteOnsetEvidence(84, 0.0, 0.42, 0.5, False),
            NoteOnsetEvidence(51, 0.5, 0.92, 3.0, True),
            NoteOnsetEvidence(69, 0.5, 0.92, 3.0, True),
            NoteOnsetEvidence(81, 0.5, 0.92, 2.8, True),
        ),
    )
    selected, audit = select_crossing_eighth_events(
        events, quarter_seconds=1.0, evidence=evidence
    )
    assert [(item.start_sec, item.pitch) for item in selected] == [
        (0.0, 48),
        (0.0, 72),
        (0.5, 51),
        (0.5, 69),
        (0.5, 81),
    ]
    assert audit["harmonic_rejected_count"] == 1
    assert audit["dropped_count"] == 1
    assert any(item["pitch"] == 81 for item in audit["duration_changes"]) or any(
        item.pitch == 81 for item in selected
    )


def test_two_real_c4_attacks_are_not_collapsed() -> None:
    events = [
        NoteEvent(2.0, 2.42, 60, 88, 0.9),
        NoteEvent(2.0, 2.65, 60, 78, 0.8),
    ]
    selected, audit = select_crossing_eighth_events(events, quarter_seconds=1.0)
    assert len(selected) == 2
    assert all(item.pitch == 60 for item in selected)
    assert all(item.start_sec == pytest.approx(2.0) for item in selected)
    assert all(abs(item.end_sec - item.start_sec - 0.5) < 1e-6 for item in selected)
    assert audit["dropped_count"] == 0


def test_unconfirmed_observation_cannot_delete_a_weak_simultaneous_note() -> None:
    weak = NoteEvent(0.03, 0.7, 72, 40, 0.4)
    bass = NoteEvent(0.03, 0.7, 48, 90, 0.9)
    observation = HarmonicRemoval(48, 72, 0.03, 0.7, 4, 0.0, 0.1, False)
    evidence = HarmonicEvidence(
        version="test", status="available", source="AUDIO_STFT", removals=(),
        observations=(observation,),
        onset_observations=(
            NoteOnsetEvidence(48, 0.03, 0.7, 3.0, True),
            NoteOnsetEvidence(72, 0.03, 0.7, 1.1, False),
        ),
    )
    selected, audit = select_crossing_eighth_events([weak, bass], 1.0, evidence)
    assert Counter(n.pitch for n in selected) == Counter([48, 72])
    assert audit["removals"] == []
    assert audit["status"] == "needs_review"
    assert audit["unconfirmed_event_indices"] == [0]


def test_audio_evidence_is_matched_before_quantization_and_not_reused_for_reattack() -> None:
    alias = NoteEvent(0.09, 0.6, 84, 30, 0.3)
    reattack = NoteEvent(0.15, 0.8, 84, 60, 0.6)
    evidence = HarmonicEvidence(
        version="test", status="available", source="AUDIO_STFT",
        removals=(HarmonicRemoval(72, 84, 0.09, 0.6, 2, 0.0, 0.1, False),),
    )
    events = [alias, reattack, NoteEvent(0.04, 0.7, 72, 90, 0.9)]
    selected, audit = select_crossing_eighth_events(events, 1.0, evidence)
    assert len(selected) == 2
    assert [n.pitch for n in selected] == [72, 84]
    assert [r["input_index"] for r in audit["removals"]] == [0]
    assert [r["input_index"] for r in audit["retained"]] == [1, 2]
    scored = build_score(events, harmonic_evidence=evidence, notation_context=_crossing_context())
    assert Counter(n.pitch for n in scored.notation_notes) == Counter([72, 84])


def test_large_snap_is_audited_and_never_silently_drops_an_off_grid_event() -> None:
    event = NoteEvent(9.2351, 9.3677, 81, 42, 0.33)
    selected, audit = select_crossing_eighth_events([event], 1.0)
    assert [(n.start_sec, n.end_sec, n.pitch) for n in selected] == [(9.0, 9.5, 81)]
    assert audit["large_shift_event_indices"] == [0]
    assert audit["status"] == "needs_review"
    assert audit["duration_changes"][0]["from_start_sec"] == event.start_sec


@pytest.mark.parametrize("period", [0, -1, float("nan"), float("inf")])
def test_invalid_period_is_rejected(period) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        select_crossing_eighth_events([], period)


def test_actual_xml_midi_and_timeline_keep_timing_with_detected_double_tempo(tmp_path) -> None:
    # The real detector reports ~120 BPM with a late first beat. Notation uses 60 BPM.
    analysis = replace(
        fallback_analysis(AnalysisConfig(), "test"), bpm=117.45, duration_seconds=8,
        beat_grid_seconds=tuple(0.534 + i * 0.499 for i in range(16)),
        downbeat_grid_seconds=(0.046, 2.04, 4.04, 6.04),
    )
    events = _source_cycle_events(cycles=2)
    scored = build_score(events, analysis=analysis, notation_context=_crossing_context())
    xml_path, midi_path, timeline_path = (tmp_path / name for name in (
        "score.musicxml", "score.mid", "timeline.json"
    ))
    write_musicxml(scored, xml_path)
    write_quantized_midi(scored, midi_path)
    write_timeline(scored, timeline_path)
    parsed = converter.parse(xml_path)
    expected = Counter((n.start_sec, n.pitch, 0.5) for n in events)
    xml_events = Counter(
        (float(n.getOffsetInHierarchy(part)), p.midi, float(n.quarterLength))
        for part in parsed.parts for n in part.recurse().notes for p in n.pitches
    )
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    midi_events = Counter(
        (n.start, n.pitch, n.end - n.start) for i in midi.instruments for n in i.notes
    )
    assert xml_events == midi_events == expected
    assert len(parsed.parts) == 2
    timeline = json.loads(timeline_path.read_text())
    assert timeline["analysis"]["bpm"] == 117.45
    assert timeline["tempo_bpm"] == 60
    assert timeline["beat_grid_seconds"][:3] == [0.0, 1.0, 2.0]
    assert timeline["analysis"]["beat_grid_seconds"][0] == 0.534
    assert timeline["reconstruction"]["pickup"]["measure_offset_units"] == 0
