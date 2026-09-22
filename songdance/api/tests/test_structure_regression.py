import json
from pathlib import Path

from scripts.evaluate_structure import _fingerprint


def test_saved_structure_regression_passes_phase14_gates() -> None:
    path = Path(__file__).parent / "fixtures/audio/structure-results.json"
    report = json.loads(path.read_text(encoding="utf-8"))

    assert report["total_count"] == 16
    assert report["gate"]["status"] == "passed"
    assert report["summary"]["p95_elapsed_seconds"] <= 15
    assert report["summary"]["time_signature_accuracy"] >= 0.75
    assert report["summary"]["stable_count"] == 16
    assert report["summary"]["median_bpm_error"] <= 5
    assert report["summary"]["bpm_accuracy_within_5"] >= 0.75
    assert report["summary"]["mean_downbeat_alignment_error_ms"] <= 250


def test_saved_structure_regression_keeps_critical_meter_cases() -> None:
    path = Path(__file__).parent / "fixtures/audio/structure-results.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    by_pattern = {item["pattern"]: item for item in report["results"]}

    assert by_pattern["waltz_34"]["time_signature"] == "3/4"
    assert by_pattern["compound_68"]["time_signature"] == "6/8"
    assert by_pattern["waltz_34"]["downbeat_alignment_error_ms"] <= 100
    assert by_pattern["compound_68"]["downbeat_alignment_error_ms"] <= 100
    assert all(item["stable"] for item in report["results"])
    assert all(item["key_confidence"] is not None for item in report["results"])
    assert all(item["beat_alignment_error_ms"] is not None for item in report["results"])
    assert all(item["downbeat_alignment_error_ms"] is not None for item in report["results"])


def test_saved_structure_regression_fingerprint_is_current() -> None:
    path = Path(__file__).parent / "fixtures/audio/structure-results.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    stable = {
        key: value for key, value in report.items() if key not in {"generated_at", "evaluation_id"}
    }

    assert report["evaluation_id"] == _fingerprint(stable)


def test_phase29_expert_failure_baseline_is_preserved() -> None:
    baseline = json.loads(
        (
            Path(__file__).parent / "fixtures/audio/structure-review-phase29-expert-baseline.json"
        ).read_text(encoding="utf-8")
    )

    assert baseline["case_id"] == "04-arpeggios"
    assert baseline["rating"] == "needs_redo"
    assert {finding["code"] for finding in baseline["findings"]} == {
        "FALSE_PICKUP",
        "SHIFTED_BARLINES",
        "SUSTAIN_AS_POLYPHONY",
        "UNSTABLE_HAND_SPLIT",
        "HARMONIC_AS_PLAYED_NOTE",
    }


def test_phase36_07_soft_failure_and_repaired_structure_are_explicit() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    review = json.loads((fixture_root / "structure-review.json").read_text(encoding="utf-8"))
    result = next(item for item in review["results"] if item["id"] == "07-soft")
    assert result["rating"] == "needs_redo"
    historical = json.loads(
        (fixture_root / "structure-review-phase36-07-soft-baseline.json").read_text()
    )
    assert {finding["code"] for finding in historical["reviewer_notes"]} == {
        "FALSE_PICKUP_QUARTER_NOTE",
        "LEADING_TONE_ABSENT_KEY_MISREAD",
        "RESONANCE_AS_NOTE_DURATION",
    }

    timeline = json.loads(
        (fixture_root / "structure-review-artifacts/07-soft/timeline.json").read_text(
            encoding="utf-8"
        )
    )
    assert timeline["analysis"]["key_signature"] == "C major"
    assert timeline["analysis"]["key_signature_source"] == "default"
    assert "KEY_SIGNATURE_DEFAULTED_C_MAJOR" in timeline["analysis"]["reason_codes"]
    assert timeline["reconstruction"]["pickup"]["measure_offset_units"] == 0
    assert (
        "FALSE_PICKUP_REJECTED_FULL_MEASURE" in timeline["reconstruction"]["pickup"]["reason_codes"]
    )
    assert (
        "MONOPHONIC_RESONANCE_CAPPED"
        in timeline["reconstruction"]["voice_compression"]["reason_codes"]
    )
    durations = [
        round(item["end_sec"] - item["start_sec"], 6)
        for item in timeline["notation_notes"]
        if item["pitch"] < 96
    ]
    assert max(durations) <= 0.75
    baseline = json.loads(
        (fixture_root / "structure-review-phase36-07-soft-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    assert baseline["rating"] == "needs_redo"
    assert baseline["re_review"]["rating"] == "minor_edits"
    assert baseline["resolution"]["status"] == "resolved_pending_full_suite_review"
