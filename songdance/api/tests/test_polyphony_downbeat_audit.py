import json

import pytest

from scripts.audit_polyphony_downbeats import diagnose, run
from scripts.piano_comparison_cases import ROOT


def chord(start):
    return [
        {"pitch": p, "start_sec": start, "end_sec": start + 1, "velocity": 80} for p in (55, 60, 64)
    ]


def test_regular_chords_support_hypothesis_without_claiming_audio_detection():
    result = diagnose(chord(0.01) + chord(2.01) + chord(4.01))
    assert result["candidate_count"] == 3
    assert result["all_adjacent_intervals_near_measure"]
    assert result["all_candidates_near_hypothesized_downbeat"]
    assert result["audio_downbeat_detection_verified"] is False


def test_weak_beat_chords_are_reported_not_snapped():
    result = diagnose(chord(1) + chord(3) + chord(5))
    assert result["all_adjacent_intervals_near_measure"]
    assert not result["all_candidates_near_hypothesized_downbeat"]
    assert result["actual_note_changes"] == 0


def test_missing_cycle_and_nonchord_do_not_pass():
    assert not diagnose(chord(0) + chord(4))["all_adjacent_intervals_near_measure"]
    assert diagnose(chord(0)[:2])["candidate_count"] == 0


def test_chain_of_close_notes_cannot_grow_cluster_beyond_window():
    notes = chord(0)
    for n, start in zip(notes, (0, 0.07, 0.14), strict=True):
        n["start_sec"] = start
    assert diagnose(notes)["candidate_count"] == 0


def test_live_audit_preserves_all_files_and_rejects_overwrite(tmp_path):
    report = run(tmp_path / "report")
    stored = ROOT / "tests/fixtures/audio/candidates/16-downbeat-audit-v2/audit.json"
    assert report == json.loads(stored.read_text())
    assert report["raw"]["candidate_count"] == 15
    assert report["raw"]["all_candidates_near_hypothesized_downbeat"]
    assert report["production_eligible"] is False
    with pytest.raises(ValueError, match="already exists"):
        run(tmp_path / "report")
