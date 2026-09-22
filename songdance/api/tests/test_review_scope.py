import json

from scripts.compare_piano_model_outputs import read_midi
from scripts.human_quality_gate import file_sha256
from scripts.plan_review_scope import changes, visible
from scripts.rebuild_review_isolated import SOURCE


def event(pitch, start=0, end=1, velocity=80):
    return {"pitch": pitch, "start_sec": start, "end_sec": end, "velocity": velocity}


def test_changes_separates_pitch_timing_and_velocity():
    baseline = [event(60)]
    timing = changes(baseline, [event(60, 0, 2)])
    assert timing["timing_changed"] and not timing["pitch_counts_changed"]
    velocity = changes(baseline, [event(60, velocity=50)])
    assert velocity["velocity_changed"] and not velocity["timing_changed"]
    assert changes(baseline, [event(62)])["pitch_counts_changed"]


def test_actual_scope_recomputes_without_granting_ratings():
    root = SOURCE / "candidates/closeout-review-20260922-v1"
    report = json.loads((root / "review-scope.json").read_text())
    assert report["difference_report_sha256"] == file_sha256(root / "differences.json")
    assert len(report["cases"]) == 26 and report["production_eligible"] is False
    for row in report["cases"]:
        old = SOURCE / f"{row['suite']}-review-artifacts" / row["case_id"]
        new = root / f"{row['suite']}-review-artifacts" / row["case_id"]
        actual = changes(read_midi(old / "score.mid"), read_midi(new / "score.mid"))
        assert all(row[k] == v for k, v in actual.items())
        assert row["visible_metadata_changed"] == (
            visible(old / "score.musicxml") != visible(new / "score.musicxml")
        )
        assert row["rating"] == "pending"
