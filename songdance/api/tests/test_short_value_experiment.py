from app.pipeline.transcribe import NoteEvent
from scripts.evaluate_short_value_experiment import build_comparison, rescale_events


def _run(precision: float, recall: float, f1: float, elapsed_ms: int) -> dict[str, object]:
    return {
        "elapsed_ms": elapsed_ms,
        "process_peak_memory_mb": 128.0,
        "metrics": {"precision": precision, "recall": recall, "f1": f1},
        "events": [],
    }


def test_half_speed_events_are_restored_to_the_original_time_axis() -> None:
    restored = rescale_events([NoteEvent(2.0, 3.0, 60, 80, 0.9)], 0.5)

    assert restored == [NoteEvent(1.0, 1.5, 60, 80, 0.9)]


def test_half_speed_candidate_stays_blocked_until_human_review() -> None:
    results = [
        {
            "original_speed": _run(0.9, 0.7, 0.7875, 100),
            "half_speed": _run(0.9, 0.8, 0.8471, 220),
        }
        for _ in range(3)
    ]

    comparison = build_comparison(results)

    assert comparison["machine_gate_passed"] is True
    assert comparison["production_eligible"] is False
    assert comparison["blocking_reasons"] == ["HUMAN_READABILITY_PENDING"]


def test_half_speed_candidate_fails_when_latency_or_precision_regresses() -> None:
    results = [
        {
            "original_speed": _run(0.9, 0.7, 0.7875, 100),
            "half_speed": _run(0.85, 0.8, 0.8226, 300),
        }
        for _ in range(3)
    ]

    comparison = build_comparison(results)

    assert comparison["machine_gate_passed"] is False
    assert comparison["production_eligible"] is False
    assert comparison["blocking_reasons"] == [
        "MACHINE_METRIC_GATE_FAILED",
        "HUMAN_READABILITY_PENDING",
    ]
