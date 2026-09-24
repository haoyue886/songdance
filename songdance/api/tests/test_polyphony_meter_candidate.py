import json
from copy import deepcopy

import pretty_midi
import pytest

from scripts import build_polyphony_meter_candidate as builder
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def test_current_run_preserves_notes_and_seconds_with_two_four_meter(tmp_path):
    out = tmp_path / "new"
    report = builder.run(out)
    midi = pretty_midi.PrettyMIDI(str(out / "candidate.mid"))
    assert midi.get_tempo_changes()[1].tolist() == [60]
    assert [(s.numerator, s.denominator, s.time) for s in midi.time_signature_changes] == [
        (2, 4, 0)
    ]
    assert midi.get_downbeats()[:4].tolist() == [0, 2, 4, 6]
    original = ROOT / "tests/fixtures/audio/structure-review-artifacts/16-noisy-polyphony/raw.mid"
    before, after = read_midi(original), read_midi(out / "candidate.mid")
    assert len(before) == len(after) == 149
    assert builder.verify_roundtrip(before, after) <= builder.MAX_TICK_ERROR_SECONDS
    assert file_sha256(original) == report["original_midi_sha256"]
    assert report["actual_note_additions"] == report["actual_note_deletions"] == 0
    assert report["applied_quantization"] is False
    assert report["production_eligible"] is False
    for metrics in report["metrics_onsets_only"].values():
        for field in ("matched_count", "extra_count", "missing_count"):
            assert metrics["before"][field] == metrics["after"][field]
    assert report["metrics_onsets_only"]["0.1"]["after"]["matched_count"] == 120
    assert report["metrics_onsets_only"]["0.1"]["after"]["extra_count"] == 29
    assert json.loads((out / "audit.json").read_text()) == report
    with pytest.raises(ValueError, match="output exists"):
        builder.run(out)


@pytest.mark.parametrize("mutation", ("pitch", "duration", "velocity", "count"))
def test_roundtrip_mutations_fail_instead_of_claiming_timing_preserved(mutation):
    before = [{"pitch": 60, "velocity": 80, "start_sec": 0.5, "end_sec": 1.3}]
    after = deepcopy(before)
    if mutation == "pitch":
        after[0]["pitch"] = 62
    elif mutation == "duration":
        after[0]["end_sec"] += 0.1
    elif mutation == "velocity":
        after[0]["velocity"] = 70
    else:
        after.append(deepcopy(after[0]))
    with pytest.raises(ValueError):
        builder.verify_roundtrip(before, after)


def test_output_failure_keeps_failed_status(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("controlled export failure")

    monkeypatch.setattr(builder.pretty_midi.PrettyMIDI, "write", fail)
    output = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="controlled"):
        builder.run(output)
    assert json.loads((output / "audit.json").read_text())["status"] == "failed"


def test_weak_beat_position_is_reported_not_silently_snapped():
    result = builder.beat_position(3.0)
    assert result["quarter_offset"] == 1
    assert abs(result["distance_from_nearest_downbeat_seconds"]) == 1
