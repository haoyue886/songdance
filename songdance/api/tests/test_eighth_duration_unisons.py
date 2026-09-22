from app.pipeline.score import _cap_eighth_note_durations
from app.pipeline.transcribe import NoteEvent


def event(start, end, pitch):
    return NoteEvent(start, end, pitch, 80, 0.8)


def test_simultaneous_notes_do_not_truncate_each_other_to_zero():
    source = [event(0, 0.8, 60), event(0, 0.8, 72), event(0.5, 1.3, 62)]
    result = _cap_eighth_note_durations(source, 1)
    assert [(n.start_sec, n.end_sec, n.pitch) for n in result] == [
        (0, 0.5, 60),
        (0, 0.5, 72),
        (0.5, 1, 62),
    ]
    assert source[0].end_sec == 0.8


def test_same_key_unisons_and_short_notes_are_preserved():
    source = [event(0, 0.2, 60), event(0, 0.8, 60)]
    result = _cap_eighth_note_durations(source, 1)
    assert [n.end_sec for n in result] == [0.2, 0.5]
    assert len(result) == 2


def test_empty_and_sequential_input_keep_existing_policy():
    assert _cap_eighth_note_durations([], 1) == []
    source = [event(0, 0.8, 60), event(0.5, 0.7, 62)]
    assert [n.end_sec for n in _cap_eighth_note_durations(source, 1)] == [0.5, 0.7]


def test_actual_dynamics_candidate_preserves_positive_model_events():
    import json
    from pathlib import Path

    from scripts.compare_piano_model_outputs import read_midi

    fixtures = Path(__file__).parent / "fixtures/audio"
    candidate = fixtures / "candidates/08-positive-duration-v1"
    previous = (
        fixtures / "candidates/closeout-review-20260922-v1/structure-review-artifacts/08-dynamics"
    )
    assert read_midi(candidate / "raw.mid") == read_midi(previous / "raw.mid")
    report = json.loads((candidate / "validation.json").read_text())
    timeline = json.loads((candidate / "timeline.json").read_text())
    assert report["production_eligible"] is False
    assert all(n["end_sec"] > n["start_sec"] for n in timeline["notes"])
    assert report["metrics"]["matched_count"] == 53
    assert report["metrics"]["extra_count"] == 41
    assert report["metrics"]["missing_count"] == 6
    assert len(read_midi(candidate / "score.mid")) == 94


def test_unsorted_events_and_long_gaps_keep_next_distinct_attack_policy():
    source = [event(2, 3, 64), event(0, 3, 60), event(0, 0.2, 72)]
    result = _cap_eighth_note_durations(source, 1)
    assert [(n.pitch, n.start_sec, n.end_sec) for n in result] == [
        (60, 0, 2),
        (72, 0, 0.2),
        (64, 2, 2.5),
    ]
    assert source[0].start_sec == 2
    assert source[1].end_sec == 3


def test_near_simultaneous_attacks_are_not_silently_merged():
    source = [event(0, 1, 60), event(1e-10, 1, 64)]
    result = _cap_eighth_note_durations(source, 1)
    assert len(result) == 2
    assert result[0].end_sec == 1e-10
    assert all(n.end_sec > n.start_sec for n in result)
