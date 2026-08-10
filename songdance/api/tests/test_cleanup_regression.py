import json
from pathlib import Path


def test_saved_cleanup_regression_preserves_raw_recall() -> None:
    report_path = Path(__file__).parent / "fixtures/audio/regression-results.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["cleanup_gate"] == {
        "status": "passed",
        "minimum_recall_delta": -0.05,
    }
    assert report["machine_summary"]["cleanup_recall_delta"] >= -0.05
    assert all(item["cleanup_recall_delta"] >= -0.05 for item in report["results"])
    assert all(item["cleanup"]["status"] == "applied" for item in report["results"])
    assert all(
        item["cleanup"]["source_note_count"] == item["raw_estimated_notes"]
        for item in report["results"]
    )


def test_phase11_human_review_baseline_is_preserved() -> None:
    baseline_path = (
        Path(__file__).parent / "fixtures/audio/human-review-phase11-baseline.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    usable = sum(item["rating"] != "needs_redo" for item in baseline["results"])
    assert usable == 4
    assert baseline["reviewer"]["midi_daw_experience"] is True
    assert baseline["suite_fingerprint"]
