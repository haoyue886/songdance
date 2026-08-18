import json
from dataclasses import replace
from pathlib import Path

import pretty_midi
import pytest
from music21 import converter, stream

from app.pipeline.analysis import AnalysisConfig, fallback_analysis
from app.pipeline.quantize import FALSE_PICKUP_REJECTED_FULL_MEASURE
from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.transcribe import NoteEvent


def _analysis(*, downbeat: float = 0.5):
    return replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        bpm=120,
        beat_grid_seconds=tuple(index * 0.5 for index in range(13)),
        downbeat_grid_seconds=(downbeat, downbeat + 2, downbeat + 4),
        time_signature="4/4",
        time_signature_source="fixture",
    )


def test_pickup_measure_is_not_rendered_as_a_full_leading_rest(tmp_path) -> None:
    scored = build_score(
        [NoteEvent(0.0, 0.5, 60, 90, 0.9), NoteEvent(0.5, 1.0, 64, 90, 0.9)],
        analysis=_analysis(),
    )
    destination = tmp_path / "pickup.musicxml"
    write_musicxml(scored, destination)

    parsed = converter.parse(str(destination))
    first_measure = list(parsed.parts[0].getElementsByClass(stream.Measure))[0]
    assert first_measure.paddingLeft == 3
    assert first_measure.duration.quarterLength == 1
    assert score_structure_errors(parsed, validate_measure_durations=True) == []


def test_pickup_measure_uses_one_shared_boundary_for_both_hands() -> None:
    scored = build_score(
        [NoteEvent(0.0, 0.5, 48, 90, 0.9), NoteEvent(0.25, 0.5, 72, 90, 0.9)],
        analysis=_analysis(),
    )

    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]
    assert [measure.paddingLeft for measure in first_measures] == [3, 3]
    assert [measure.duration.quarterLength for measure in first_measures] == [1, 1]
    right_rests = list(first_measures[0].recurse().getElementsByClass("Rest"))
    assert [rest.quarterLength for rest in right_rests] == [0.5]
    assert score_structure_errors(scored.score, validate_measure_durations=True) == []


def test_pickup_trims_a_full_leading_rest_when_the_other_hand_is_empty() -> None:
    scored = build_score([NoteEvent(0.0, 0.5, 72, 90, 0.9)], analysis=_analysis())

    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]
    assert [measure.paddingLeft for measure in first_measures] == [3, 3]
    assert [measure.duration.quarterLength for measure in first_measures] == [1, 1]
    assert score_structure_errors(scored.score, validate_measure_durations=True) == []


def test_complete_eighth_note_cycles_reject_false_pickup() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(
            index * 0.25,
            index * 0.25 + 0.2,
            pitches[index % len(pitches)],
            96 if index == 0 else 84,
            0.9,
        )
        for index in range(24)
    ]

    scored = build_score(events, analysis=_analysis(downbeat=0.25))
    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]

    assert [measure.paddingLeft for measure in first_measures] == [0, 0]
    assert [measure.duration.quarterLength for measure in first_measures] == [4, 4]
    assert scored.reconstruction["pickup"] == {
        "measure_offset_units": 0,
        "applied": False,
        "reason_codes": (FALSE_PICKUP_REJECTED_FULL_MEASURE,),
        "candidate_pickup_units": 2,
        "first_measure_occupied_slots": 8,
        "complete_cycle_count": 3,
        "matching_complete_cycles": 3,
        "cycle_match_ratio": 1.0,
        "first_onset_velocity": 96,
        "candidate_downbeat_velocity": 84,
    }
    assert [event.start_sec for event in scored.notes] == pytest.approx(
        [index * 0.25 for index in range(24)]
    )
    assert score_structure_errors(scored.score, validate_measure_durations=True) == []


def test_quiet_eighth_note_pickup_is_preserved() -> None:
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.2, 60 + index % 5, 40 if index == 0 else 90, 0.9)
        for index in range(24)
    ]

    scored = build_score(events, analysis=_analysis(downbeat=0.25))
    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]

    assert [measure.paddingLeft for measure in first_measures] == [3.5, 3.5]
    assert scored.reconstruction["pickup"]["applied"] is True
    assert scored.reconstruction["pickup"]["reason_codes"] == ()


def test_sparse_half_slot_onsets_cannot_fill_two_eighth_note_slots() -> None:
    starts = [
        *(index * 0.25 for index in range(8)),
        2.125,
        2.625,
        3.125,
        3.625,
        4.125,
        4.625,
        5.125,
        5.625,
    ]
    events = [
        NoteEvent(start, start + 0.2, 60 + index % 5, 96 if index == 0 else 84, 0.9)
        for index, start in enumerate(starts)
    ]

    scored = build_score(events, analysis=_analysis(downbeat=0.25))

    assert scored.reconstruction["pickup"]["applied"] is True
    assert scored.reconstruction["pickup"]["reason_codes"] == ()


def test_arpeggio_musicxml_barlines_match_every_complete_truth_cycle() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    truth_midi = pretty_midi.PrettyMIDI(str(fixture_root / "generated/04-arpeggios.mid"))
    truth_notes = sorted(
        (item for instrument in truth_midi.instruments for item in instrument.notes),
        key=lambda item: (item.start, item.pitch),
    )
    tempo_times, tempi = truth_midi.get_tempo_changes()
    complete_cycles = len(truth_notes) // 8

    assert tempo_times.tolist() == [0.0]
    assert tempi.tolist() == [120.0]
    assert complete_cycles == 14
    assert all(
        [item.pitch for item in truth_notes[cycle * 8 : (cycle + 1) * 8]]
        == [48, 55, 60, 64, 67, 72, 67, 64]
        for cycle in range(complete_cycles)
    )
    assert all(
        truth_notes[index + 1].start - truth_notes[index].start == pytest.approx(0.25)
        for index in range(complete_cycles * 8 - 1)
    )

    score = converter.parse(
        str(fixture_root / "structure-review-artifacts/04-arpeggios/score.musicxml")
    )
    seconds_per_quarter = 60 / tempi[0]
    expected_boundaries = [
        truth_notes[cycle * 8].start / seconds_per_quarter for cycle in range(complete_cycles)
    ]
    part_boundaries = []
    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        assert all(measure.paddingLeft == 0 for measure in measures)
        assert all(measure.duration.quarterLength == 4 for measure in measures)
        boundaries = [float(measure.offset) for measure in measures[:complete_cycles]]
        assert boundaries == expected_boundaries
        for measure in measures[:complete_cycles]:
            assert {
                float(item.offset) for item in measure.recurse().notes
            } <= {index * 0.5 for index in range(8)}
        part_boundaries.append(boundaries)

    assert part_boundaries[0] == part_boundaries[1]
    expected_onsets = {index * 0.5 for index in range(8)}
    for measure_index in range(complete_cycles):
        actual_onsets = {
            float(item.offset)
            for part in score.parts
            for item in list(part.getElementsByClass(stream.Measure))[
                measure_index
            ].recurse().notes
        }
        assert actual_onsets == expected_onsets

    timeline = json.loads(
        (fixture_root / "structure-review-artifacts/04-arpeggios/timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert timeline["reconstruction"]["pickup"] == {
        "measure_offset_units": 0,
        "applied": False,
        "reason_codes": ["FALSE_PICKUP_REJECTED_FULL_MEASURE"],
        "candidate_pickup_units": 2,
        "first_measure_occupied_slots": 8,
        "complete_cycle_count": 14,
        "matching_complete_cycles": 14,
        "cycle_match_ratio": 1.0,
        "first_onset_velocity": 100,
        "candidate_downbeat_velocity": 92,
    }
