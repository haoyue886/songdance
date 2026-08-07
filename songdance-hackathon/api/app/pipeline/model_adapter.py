from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

from app.pipeline.transcribe import NoteEvent


@dataclass(frozen=True)
class ModelNote:
    start_sec: float
    end_sec: float
    pitch: int
    velocity: int
    confidence: float


@dataclass(frozen=True)
class ModelRunMetrics:
    elapsed_ms: int
    peak_memory_mb: int | None = None

    def __post_init__(self) -> None:
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must not be negative")
        if self.peak_memory_mb is not None and self.peak_memory_mb < 0:
            raise ValueError("peak_memory_mb must not be negative")


@dataclass(frozen=True)
class NormalizedModelResult:
    model_version: str
    events: tuple[NoteEvent, ...]
    raw_midi: bytes
    confidence_semantics: str
    metrics: ModelRunMetrics

    def __post_init__(self) -> None:
        if not self.model_version:
            raise ValueError("model_version must not be empty")
        if not self.raw_midi:
            raise ValueError("raw_midi must not be empty")
        if not self.confidence_semantics:
            raise ValueError("confidence_semantics must not be empty")


def normalize_notes(notes: Iterable[ModelNote]) -> tuple[NoteEvent, ...]:
    """Normalize candidate output before it enters shared quality evaluation."""
    events = [
        NoteEvent(
            start_sec=float(note.start_sec),
            end_sec=float(note.end_sec),
            pitch=int(note.pitch),
            velocity=int(note.velocity),
            confidence=float(note.confidence),
        )
        for note in notes
    ]
    for event in events:
        if not all(
            isfinite(value)
            for value in (event.start_sec, event.end_sec, event.confidence)
        ):
            raise ValueError("candidate note values must be finite")
        if event.end_sec <= event.start_sec:
            raise ValueError("candidate notes must have a positive duration")
        if not 0 <= event.pitch <= 127:
            raise ValueError("candidate note pitch must be between 0 and 127")
        if not 1 <= event.velocity <= 127:
            raise ValueError("candidate note velocity must be between 1 and 127")
        if not 0 <= event.confidence <= 1:
            raise ValueError("candidate note confidence must be between 0 and 1")
    return tuple(sorted(events, key=_event_sort_key))


def _event_sort_key(event: NoteEvent) -> tuple[float, float, int, int, float]:
    return (
        event.start_sec,
        event.end_sec,
        event.pitch,
        event.velocity,
        event.confidence,
    )
