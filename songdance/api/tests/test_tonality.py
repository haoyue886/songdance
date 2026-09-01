from app.pipeline.tonality import (
    LEADING_TONE_ABSENT,
    TONICIZATION,
    UNSUPPORTED_MODE,
    TonalityConfig,
    analyze_local_tonality,
)
from app.pipeline.transcribe import NoteEvent


def _events(groups: list[tuple[float, tuple[int, ...]]]) -> list[NoteEvent]:
    return [
        NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        for start, pitches in groups
        for pitch in pitches
    ]


def test_no_cadence_returns_top_two_candidates_without_notation() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (60,)), (0.5, (62,)), (1.0, (64,))]),
        ({"value": "G major"}, {"value": "C major"}),
    )

    assert len(result.candidates) == 2
    assert result.selected is None
    assert result.notation_eligible is False
    assert TONICIZATION in result.reason_codes
    assert sum(float(item["score"]) for item in result.candidates) == 1.0
    assert "harmonic_evidence" in result.evidence
    assert result.evidence["harmonic_evidence"]["structural_tonic_returns"] == []


def test_authentic_v_to_i_can_enable_notation() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (55, 59, 62)), (1.0, (60, 64, 67))]),
        ({"value": "C major"}, {"value": "G major"}),
        config=TonalityConfig(minimum_notation_score=0.5),
    )

    assert result.selected == "C major"
    assert result.notation_eligible is True
    assert result.evidence["cadence"]["type"] == "authentic_cadence"
    assert sorted(result.evidence["harmonic_evidence"]["chord_roots"]) == [0, 7]
    assert result.evidence["harmonic_evidence"]["structural_tonic_returns"] == [0]


def test_single_secondary_dominant_is_tonicization_only() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (57, 61, 64)), (1.0, (62, 66, 69)), (2.0, (60, 64, 67))]),
        ({"value": "D major"}, {"value": "C major"}),
    )

    assert result.selected is None
    assert result.notation_eligible is False
    assert TONICIZATION in result.reason_codes


def test_missing_leading_tone_blocks_sharp_key_notation() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (67,)), (0.5, (69,)), (1.0, (71,))]),
        ({"value": "G major"}, {"value": "C major"}),
    )

    assert result.selected is None
    assert result.notation_eligible is False
    assert LEADING_TONE_ABSENT in result.reason_codes


def test_unknown_mode_is_rejected_instead_of_scored_as_major() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (55, 59, 62)), (1.0, (60, 64, 67))]),
        ({"value": "C dorian"},),
    )

    assert result.selected is None
    assert UNSUPPORTED_MODE in result.reason_codes


def test_single_onset_returns_a_stable_non_crashing_contract() -> None:
    result = analyze_local_tonality(
        _events([(0.0, (60,))]),
        ({"value": "C major"},),
    )

    assert result.selected is None
    assert result.evidence["harmonic_evidence"]["bass_pitch_classes"] == [0]
