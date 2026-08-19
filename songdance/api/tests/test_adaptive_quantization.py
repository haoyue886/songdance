import json
from dataclasses import replace
from pathlib import Path

import pytest
from music21 import converter, note, stream

from app.pipeline.adaptive_quantization import (
    DEFAULT_SIXTEENTH_GRID,
    REFERENCE_QUANTIZATION_CONTEXT,
    SHORT_VALUE_EVIDENCE,
    select_quantization,
)
from app.pipeline.analysis import AnalysisConfig, fallback_analysis
from app.pipeline.notation_context import NotationContext
from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.transcribe import NoteEvent

FIXTURE_ROOT = Path(__file__).parent / "fixtures/audio"


def _analysis():
    return replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        bpm=120,
        beat_grid_seconds=tuple(index * 0.5 for index in range(5)),
        downbeat_grid_seconds=(0.0, 2.0),
        time_signature="4/4",
        time_signature_source="fixture",
    )


def _short_value_events(divisions_per_quarter: int) -> list[NoteEvent]:
    step = 0.5 / divisions_per_quarter
    right = [
        NoteEvent(
            index * step,
            (index + 0.82) * step,
            (72, 74, 76, 77)[index % 4],
            88,
            0.95,
            hand="right",
            hand_confidence=1.0,
        )
        for index in range(divisions_per_quarter * 4)
    ]
    bass = NoteEvent(0.0, 2.0, 48, 76, 0.95, hand="left", hand_confidence=1.0)
    return [bass, *right]


@pytest.mark.parametrize(
    ("divisions", "note_type", "reason"),
    [
        (4, "16th", DEFAULT_SIXTEENTH_GRID),
        (8, "32nd", SHORT_VALUE_EVIDENCE),
        (16, "64th", SHORT_VALUE_EVIDENCE),
    ],
)
def test_adaptive_quantization_writes_short_value_truth_to_musicxml(
    tmp_path, divisions: int, note_type: str, reason: str
) -> None:
    events = _short_value_events(divisions)

    decision = select_quantization(events, _analysis())
    scored = build_score(events, analysis=_analysis())
    destination = tmp_path / f"{note_type}.musicxml"
    write_musicxml(scored, destination)
    parsed = converter.parse(str(destination))

    assert decision.divisions_per_quarter == divisions
    assert reason in decision.reason_codes
    assert scored.quantization == decision
    assert scored.reconstruction["quantization"] == decision.summary()
    assert {
        item.duration.type
        for item in parsed.recurse().getElementsByClass(note.Note)
        if item.pitch.midi >= 72
    } == {note_type}
    assert all(
        measure.duration.quarterLength == 4
        for part in parsed.parts
        for measure in part.getElementsByClass(stream.Measure)
    )
    assert score_structure_errors(parsed, validate_measure_durations=True) == []


def test_reference_score_can_hold_k545_at_sixteenth_resolution() -> None:
    events = _short_value_events(16)

    scored = build_score(
        events,
        analysis=_analysis(),
        notation_context=NotationContext(
            quantization_divisions_per_quarter=4,
            quantization_source="reference_score",
        ),
    )

    assert scored.quantization.divisions_per_quarter == 4
    assert scored.quantization.reason_codes == (REFERENCE_QUANTIZATION_CONTEXT,)


def test_short_value_truth_manifest_covers_each_supported_resolution() -> None:
    manifest = json.loads(
        (FIXTURE_ROOT / "short-value-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["suite_type"] == "synthetic_short_value_truth"
    assert {
        (case["divisions_per_quarter"], case["note_value"])
        for case in manifest["cases"]
    } == {(4, 16), (8, 32), (16, 64)}


@pytest.mark.parametrize(
    "context",
    [
        NotationContext,
        lambda: NotationContext(key_signature_source="reference_score"),
        lambda: NotationContext(key_signature="C major"),
        lambda: NotationContext(measure_offset_source="reference_score"),
        lambda: NotationContext(quantization_source="reference_score"),
        lambda: NotationContext(quantization_divisions_per_quarter=4),
    ],
)
def test_incomplete_notation_context_is_rejected(context) -> None:
    if context is NotationContext:
        assert context() == NotationContext()
        return
    with pytest.raises(ValueError):
        context()
