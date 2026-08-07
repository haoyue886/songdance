import pytest

from app.pipeline.model_adapter import (
    ModelNote,
    ModelRunMetrics,
    NormalizedModelResult,
    normalize_notes,
)


def test_normalize_notes_sorts_stably_and_preserves_metrics_contract() -> None:
    events = normalize_notes(
        [
            ModelNote(1, 1.5, 64, 80, 0.4),
            ModelNote(0, 0.5, 67, 90, 0.9),
            ModelNote(0, 0.5, 60, 100, 0.8),
        ]
    )

    assert [(event.start_sec, event.pitch) for event in events] == [(0, 60), (0, 67), (1, 64)]
    metrics = ModelRunMetrics(elapsed_ms=12, peak_memory_mb=128)
    result = NormalizedModelResult(
        model_version="candidate@commit",
        events=events,
        raw_midi=b"MThd",
        confidence_semantics="model emission probability",
        metrics=metrics,
    )
    assert result.metrics.peak_memory_mb == 128
    assert result.confidence_semantics == "model emission probability"


@pytest.mark.parametrize(
    "note",
    [
        ModelNote(1, 1, 60, 100, 0.5),
        ModelNote(0, 1, 128, 100, 0.5),
        ModelNote(0, 1, 60, 0, 0.5),
        ModelNote(0, 1, 60, 100, 1.1),
    ],
)
def test_normalize_notes_rejects_invalid_candidate_events(note: ModelNote) -> None:
    with pytest.raises(ValueError):
        normalize_notes([note])


@pytest.mark.parametrize("field", ("start_sec", "end_sec", "confidence"))
@pytest.mark.parametrize("value", (float("nan"), float("inf"), float("-inf")))
def test_normalize_notes_rejects_non_finite_values(field: str, value: float) -> None:
    fields = {
        "start_sec": 0.0,
        "end_sec": 1.0,
        "pitch": 60,
        "velocity": 100,
        "confidence": 0.5,
    }
    fields[field] = value

    with pytest.raises(ValueError, match="must be finite"):
        normalize_notes([ModelNote(**fields)])
