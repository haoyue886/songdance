import json
from collections import Counter

import pytest

from scripts.align_repeated_note_candidate import align
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def notes():
    return [
        {"pitch": 60, "start_sec": 0.02 + i * 0.25, "end_sec": 0.19 + i * 0.25, "velocity": 80}
        for i in range(24)
    ]


def test_repeated_same_key_attacks_are_not_merged():
    source = notes()
    output, audit = align(source)
    assert len(output) == 24
    assert audit["quarter_bpm"] == 120
    assert [n["pitch"] for n in output] == [60] * 24
    assert len({n["start_sec"] for n in output}) == 24
    assert all(abs(n["end_sec"] - n["start_sec"] - 0.25) < 1e-8 for n in output)
    assert [x["slot_in_measure"] for x in audit["changes"]] == list(range(8)) * 3
    assert source[0]["end_sec"] == 0.19


def test_simultaneous_higher_notes_are_retained_not_filtered_by_reference():
    source = notes() + [{**n, "pitch": 79} for n in notes()]
    result, _ = align(source)
    assert Counter(n["pitch"] for n in result) == {60: 24, 79: 24}


def test_close_same_key_attacks_fail_instead_of_silently_merging():
    source = notes() + [{"pitch": 60, "start_sec": 0.04, "end_sec": 0.16, "velocity": 40}]
    with pytest.raises(ValueError, match="collision"):
        align(source)


def test_irregular_timing_is_not_forced_to_even_grid():
    source = notes()
    for i, n in enumerate(source):
        n["start_sec"] += 0.004 * i * i
        n["end_sec"] += 0.004 * i * i
    with pytest.raises(ValueError):
        align(source)


def test_actual_candidate_recomputes_and_preserves_every_raw_event():
    root = ROOT / "tests/fixtures/audio"
    raw = root / "structure-review-artifacts/15-repeated-notes/raw.mid"
    candidate = root / "candidates/15-timing-only-v1"
    report = json.loads((candidate / "audit.json").read_text())
    original = read_midi(raw)
    output, timing = align(original)
    assert output == report["events"] and timing == report["timing"]
    assert report["raw_sha256"] == file_sha256(raw)
    assert len(output) == len(original) == 237
    assert Counter(n["pitch"] for n in original) == Counter(n["pitch"] for n in output)
    assert report["midi_sha256"] == file_sha256(candidate / "candidate.mid")
    reference = read_midi(root / "generated/15-repeated-notes.mid")
    m = note_metrics(reference, read_midi(candidate / "candidate.mid"), 0.05)
    assert m["matched_count"] == 118 and m["extra_count"] == 119 and m["missing_count"] == 0
    assert report["production_eligible"] is False


def test_actual_run_exports_bar_aligned_midi_with_reversible_audio_origin(tmp_path):
    import pretty_midi

    from scripts.align_repeated_note_candidate import run

    output = tmp_path / "candidate"
    report = run(output)
    midi = pretty_midi.PrettyMIDI(str(output / "candidate.mid"))
    assert midi.get_tempo_changes()[1].tolist() == [120]
    assert [(s.numerator, s.denominator, s.time) for s in midi.time_signature_changes] == [
        (4, 4, 0)
    ]
    parsed = read_midi(output / "candidate.mid")
    assert min(n["start_sec"] for n in parsed) == 0
    origin = report["midi_time_origin_seconds"]
    expected = sorted(report["events"], key=lambda n: (n["start_sec"], n["pitch"], n["end_sec"]))
    for actual, wanted in zip(parsed, expected, strict=True):
        assert actual["pitch"] == wanted["pitch"]
        assert actual["velocity"] == wanted["velocity"]
        assert actual["start_sec"] + origin == pytest.approx(wanted["start_sec"], abs=0.00001)
        assert actual["end_sec"] + origin == pytest.approx(wanted["end_sec"], abs=0.00001)
    slots = sorted({c["slot"] for c in report["timing"]["changes"]})
    assert set(range(0, max(slots) + 1, 8)) <= {round(t / 0.25) for t in midi.get_downbeats()}
    with pytest.raises(ValueError, match="already exists"):
        run(output)
