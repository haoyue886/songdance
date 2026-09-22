from dataclasses import replace

import pytest

from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.harmonics import (
    HarmonicEvidence,
    NoteOnsetEvidence,
)
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent
from scripts.run_structure_review import _notation_context_for_case


def example():
    # A genuine C3 followed by two re-detected pieces, while two other pitches attack.
    return [
        NoteEvent(0.2, 0.7, 48, 90, 0.9),
        NoteEvent(0.7, 1.2, 48, 40, 0.4),
        NoteEvent(0.7, 1.1, 67, 80, 0.8),
        NoteEvent(0.7, 1.1, 73, 80, 0.8),
        NoteEvent(1.2, 1.7, 48, 35, 0.35),
        NoteEvent(1.2, 1.6, 69, 80, 0.8),
    ]


def proof(events):
    return HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=tuple(
            NoteOnsetEvidence(
                e.pitch,
                e.start_sec,
                e.end_sec,
                0.6 if i in {1, 4} else 3.0,
                i not in {1, 4},
                1.0,
                0.6 if i in {1, 4} else 3.0,
                0.01 if i in {1, 4} else None,
                0.01 if i in {1, 4} else None,
            )
            for i, e in enumerate(events)
        ),
    )


def test_dual_attack_and_two_segment_tail_keep_original_indices_and_root_proof():
    events = example()
    before = list(events)
    kept, report = clean_crossing_tails(events, proof(events), 1.0)
    assert kept == [events[i] for i in [0, 2, 3, 5]]
    assert events == before
    assert report["removed_count"] == 2
    first, second = report["removals"]
    assert [r["input_index"] for r in report["removals"]] == [1, 4]
    assert second["root_input_index"] == first["root_input_index"] == 0
    assert second["predecessor_input_index"] == 1
    assert second["chain_depth"] == 2
    assert len(first["other_independent_attacks"]) == 2
    assert second["root_onset_evidence"]["independent_onset"] is True
    assert second["predecessor_onset_evidence"]["decay_fit_error"] == 0.01


@pytest.mark.parametrize(
    "field,value",
    [
        ("pre_onset_energy", None),
        ("onset_energy", None),
        ("pre_onset_energy", 0),
        ("onset_energy", -1),
        ("onset_growth", float("nan")),
        ("onset_energy", float("inf")),
        ("onset_growth", 1.1),
        ("onset_energy", 2.0),
        ("decay_fit_error", None),
        ("decay_fit_error", float("nan")),
        ("decay_fit_error", -0.1),
        ("decay_fit_error", 0.051),
        ("transient_fit_error", None),
        ("transient_fit_error", float("nan")),
        ("transient_fit_error", -0.1),
        ("transient_fit_error", 0.051),
        ("transient_fit_error", 0.011),
        ("independent_onset", True),
    ],
)
def test_missing_invalid_or_reattack_evidence_preserves_entire_chain(field, value):
    events, h = example(), proof(example())
    obs = list(h.onset_observations)
    obs[1] = replace(obs[1], **{field: value})
    kept, report = clean_crossing_tails(events, replace(h, onset_observations=tuple(obs)), 1.0)
    assert kept == events
    assert report["removals"] == []


def test_conflicting_duplicate_measurements_are_not_last_writer_wins():
    events, h = example(), proof(example())
    h = replace(h, onset_observations=(*h.onset_observations, h.onset_observations[1]))
    assert clean_crossing_tails(events, h, 1.0)[0] == events


@pytest.mark.parametrize("variant", ["no_root", "missing_attack", "sustained", "no_contact"])
def test_structural_proof_is_required(variant):
    events = example()
    if variant == "no_root":
        events = events[1:]
    elif variant == "missing_attack":
        events = [events[0], events[1], events[4]]
    elif variant == "sustained":
        events[0] = replace(events[0], end_sec=3.0)
    else:
        events[0] = replace(events[0], end_sec=0.59)
    # Retain matching observations from the original sounding events.
    h = proof(example())
    if variant in {"sustained", "no_contact"}:
        h = replace(
            h,
            onset_observations=(
                replace(h.onset_observations[0], end_sec=events[0].end_sec),
                *h.onset_observations[1:],
            ),
        )
    assert clean_crossing_tails(events, h, 1.0)[0] == events


def test_chain_is_bounded_by_two_eighths_not_two_quarters():
    events = [*example(), NoteEvent(1.7, 2.2, 48, 30, 0.3), NoteEvent(1.7, 2.1, 71, 80, 0.8)]
    h = proof(example())
    h = replace(
        h,
        onset_observations=(
            *h.onset_observations,
            NoteOnsetEvidence(48, 1.7, 2.2, 0.6, False, 1.0, 0.6, 0.01, 0.01),
            NoteOnsetEvidence(71, 1.7, 2.1, 3.0, True, 1.0, 3.0),
        ),
    )
    kept, report = clean_crossing_tails(events, h, 1.0)
    assert events[6] in kept
    assert report["removed_count"] == 2


def test_ambiguous_predecessor_or_simultaneous_same_key_is_preserved():
    events, h = example(), proof(example())
    for additional in (replace(events[0], velocity=50), replace(events[1], velocity=50)):
        extended = [*events, additional]
        kept, report = clean_crossing_tails(extended, h, 1.0)
        assert kept == extended
        assert report["removals"] == []


@pytest.mark.parametrize("h", [None, HarmonicEvidence.unavailable()])
def test_without_evidence_all_events_survive(h):
    events = example()
    kept, report = clean_crossing_tails(events, h, 1.0)
    assert kept is events
    assert report["removed_count"] == 0
    assert report["status"] == "evidence_unavailable"


@pytest.mark.parametrize("period", [0, -1, float("nan"), float("inf")])
def test_invalid_time_unit_is_rejected(period):
    with pytest.raises(ValueError, match="positive and finite"):
        clean_crossing_tails([], None, period)


def test_only_crossing_build_uses_tail_filter(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("unexpected crossing filter")

    monkeypatch.setattr("app.pipeline.score.clean_crossing_tails", fail)
    events = [NoteEvent(0, 0.5, 60, 80, 0.8), NoteEvent(0.5, 1, 64, 80, 0.8)]
    for context in (None, _notation_context_for_case({"texture_hint": "six_note_melody"})):
        scored = build_score(events, notation_context=context)
        assert scored.reconstruction["crossing_tail_cleanup"] == {"status": "not_applied"}
