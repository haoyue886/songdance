import json

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.human_quality_gate import file_sha256
from scripts.piano_comparison_cases import ROOT


def test_actual_crossing_diff_includes_timing_changes_and_retains_quality_gap():
    fixtures = ROOT / "tests/fixtures/audio"
    rebuilt = fixtures / "candidates/closeout-review-20260919-v1"
    audit = json.loads((rebuilt / "14-change-audit.json").read_text())
    reference_path = fixtures / "generated/14-hand-crossing.mid"
    reference = list({(n["start_sec"], n["pitch"]): n for n in read_midi(reference_path)}.values())
    assert audit["reference_sha256"] == file_sha256(reference_path)
    for label, folder in [
        ("old", fixtures / "structure-review-artifacts/14-hand-crossing"),
        ("new", rebuilt / "structure-review-artifacts/14-hand-crossing"),
    ]:
        assert audit[f"{label}_sha256"] == file_sha256(folder / "score.mid")
        notes = read_midi(folder / "score.mid")
        assert audit[label]["metrics"] == {
            str(t): note_metrics(reference, notes, t) for t in (0.05, 0.1)
        }
    assert audit["new"]["durations"] == [0.5]
    assert audit["old"]["durations"] != [0.5]
    assert audit["new"]["metrics"]["0.05"]["matched_count"] == 111
    assert audit["new"]["metrics"]["0.05"]["extra_count"] == 128
    timeline = json.loads(
        (rebuilt / "structure-review-artifacts/14-hand-crossing/timeline.json").read_text()
    )
    cleanup = timeline["reconstruction"]["crossing_tail_cleanup"]
    assert cleanup["removed_count"] == len(cleanup["removals"]) == 25
    assert all(
        item["reason"] == "DECAY_REDETECTED_AT_INDEPENDENT_ATTACK" for item in cleanup["removals"]
    )
    assert audit["production_eligible"] is False
