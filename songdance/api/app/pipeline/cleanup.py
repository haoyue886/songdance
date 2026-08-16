import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict, dataclass, replace

from app.pipeline.errors import NoteCleanupError
from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicEvidenceConfig,
)
from app.pipeline.transcribe import NoteEvent

CLEANUP_ALGORITHM_VERSION = "note-cleanup-v4"
LOW_CONFIDENCE_REMOVED = "LOW_CONFIDENCE_REMOVED"
SHORT_NOTE_REMOVED = "SHORT_NOTE_REMOVED"
DUPLICATE_NOTE_REMOVED = "DUPLICATE_NOTE_REMOVED"
EXCESSIVE_DURATION_CLIPPED = "EXCESSIVE_DURATION_CLIPPED"
NOTE_PRESERVED = "NOTE_PRESERVED"
ADJACENT_SAME_PITCH_PRESERVED = "ADJACENT_SAME_PITCH_PRESERVED"
OVERLAPPING_SAME_PITCH_PRESERVED = "OVERLAPPING_SAME_PITCH_PRESERVED"
HARMONIC_CANDIDATE_REMOVED = "HARMONIC_CANDIDATE_REMOVED"
CLEANUP_REASON_CODES = (
    LOW_CONFIDENCE_REMOVED,
    SHORT_NOTE_REMOVED,
    DUPLICATE_NOTE_REMOVED,
    EXCESSIVE_DURATION_CLIPPED,
    NOTE_PRESERVED,
    ADJACENT_SAME_PITCH_PRESERVED,
    OVERLAPPING_SAME_PITCH_PRESERVED,
    HARMONIC_CANDIDATE_REMOVED,
)


@dataclass(frozen=True)
class CleanupConfig:
    min_confidence: float = 0.1
    min_duration_seconds: float = 0.04
    adjacent_same_pitch_gap_seconds: float = 0.03
    max_note_duration_seconds: float = 30.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    @property
    def version(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return (
            f"{CLEANUP_ALGORITHM_VERSION}/{fingerprint}/"
            f"{HarmonicEvidenceConfig().version}"
        )


@dataclass(frozen=True)
class CleanupResult:
    events: list[NoteEvent]
    source_note_count: int
    reason_counts: dict[str, int]
    config: CleanupConfig
    harmonic_evidence: HarmonicEvidence

    def summary(self) -> dict[str, object]:
        removed = sum(
            self.reason_counts[reason]
            for reason in (
                LOW_CONFIDENCE_REMOVED,
                SHORT_NOTE_REMOVED,
                DUPLICATE_NOTE_REMOVED,
                HARMONIC_CANDIDATE_REMOVED,
            )
        )
        return {
            "status": "applied",
            "version": self.config.version,
            "config": self.config.as_dict(),
            "source_note_count": self.source_note_count,
            "output_note_count": len(self.events),
            "removed_note_count": removed,
            "clipped_note_count": self.reason_counts[EXCESSIVE_DURATION_CLIPPED],
            "merged_note_count": 0,
            "reason_counts": dict(self.reason_counts),
            "harmonic_evidence": self.harmonic_evidence.summary(),
            "fallback_used": False,
            "error_code": None,
        }


def clean_note_events(
    events: list[NoteEvent],
    config: CleanupConfig | None = None,
    *,
    harmonic_evidence: HarmonicEvidence | None = None,
) -> CleanupResult:
    active_config = config or CleanupConfig()
    active_harmonics = harmonic_evidence or HarmonicEvidence.unavailable()
    _validate_config(active_config)
    ordered = sorted(events, key=_event_sort_key)
    if not ordered:
        raise NoteCleanupError("音符清洗没有收到原始事件")
    if any(not _valid_event(event) for event in ordered):
        raise NoteCleanupError("原始音符事件包含无效数值")

    counts: Counter[str] = Counter({reason: 0 for reason in CLEANUP_REASON_CODES})
    filtered = []
    for event in ordered:
        if event.confidence < active_config.min_confidence:
            counts[LOW_CONFIDENCE_REMOVED] += 1
        elif event.end_sec - event.start_sec < active_config.min_duration_seconds:
            counts[SHORT_NOTE_REMOVED] += 1
        else:
            filtered.append(event)

    deduplicated = _deduplicate(filtered, counts)
    without_harmonics = _remove_harmonic_candidates(
        deduplicated, active_harmonics, counts
    )
    normalized = _normalize_sustain(without_harmonics, active_config, counts)
    if not normalized:
        raise NoteCleanupError("音符清洗移除了全部原始事件")
    counts[NOTE_PRESERVED] = len(normalized)
    return CleanupResult(
        events=sorted(normalized, key=_event_sort_key),
        source_note_count=len(ordered),
        reason_counts={reason: counts[reason] for reason in CLEANUP_REASON_CODES},
        config=active_config,
        harmonic_evidence=active_harmonics,
    )


def failed_cleanup_summary(
    config: CleanupConfig, source_note_count: int, error_code: str
) -> dict[str, object]:
    return {
        "status": "failed",
        "version": config.version,
        "config": config.as_dict(),
        "source_note_count": source_note_count,
        "output_note_count": source_note_count,
        "removed_note_count": 0,
        "clipped_note_count": 0,
        "merged_note_count": 0,
        "reason_counts": {reason: 0 for reason in CLEANUP_REASON_CODES},
        "harmonic_evidence": HarmonicEvidence.unavailable().summary(),
        "fallback_used": True,
        "error_code": error_code,
    }


def _deduplicate(
    events: list[NoteEvent], counts: Counter[str]
) -> list[NoteEvent]:
    groups: list[list[NoteEvent]] = []
    for event in events:
        group = next(
            (
                candidate
                for candidate in groups
                if candidate[0].pitch == event.pitch
                and candidate[0].start_sec == event.start_sec
            ),
            None,
        )
        if group is None:
            groups.append([event])
        else:
            group.append(event)

    winners = []
    for group in groups:
        winners.append(max(group, key=_winner_key))
        counts[DUPLICATE_NOTE_REMOVED] += len(group) - 1
    return sorted(winners, key=_event_sort_key)


def _normalize_sustain(
    events: list[NoteEvent], config: CleanupConfig, counts: Counter[str]
) -> list[NoteEvent]:
    normalized = []
    for event in events:
        if event.end_sec - event.start_sec > config.max_note_duration_seconds:
            event = replace(
                event,
                end_sec=round(event.start_sec + config.max_note_duration_seconds, 6),
            )
            counts[EXCESSIVE_DURATION_CLIPPED] += 1
        normalized.append(event)

    for pitch in sorted({event.pitch for event in events}):
        pitch_events = sorted(
            (event for event in normalized if event.pitch == pitch), key=_event_sort_key
        )
        previous = pitch_events[0]
        for event in pitch_events[1:]:
            gap = event.start_sec - previous.end_sec
            if event.start_sec < previous.end_sec:
                counts[OVERLAPPING_SAME_PITCH_PRESERVED] += 1
            elif gap <= config.adjacent_same_pitch_gap_seconds:
                counts[ADJACENT_SAME_PITCH_PRESERVED] += 1
            else:
                previous = event
                continue
            previous = event
    return normalized


def _remove_harmonic_candidates(
    events: list[NoteEvent],
    evidence: HarmonicEvidence,
    counts: Counter[str],
) -> list[NoteEvent]:
    if evidence.status != "available" or not evidence.removals:
        return events
    kept = [
        event
        for event in events
        if not any(removal.matches(event) for removal in evidence.removals)
    ]
    counts[HARMONIC_CANDIDATE_REMOVED] += len(events) - len(kept)
    return kept


def _validate_config(config: CleanupConfig) -> None:
    values = config.as_dict()
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError("cleanup thresholds must be finite")
    if not 0 <= config.min_confidence <= 1:
        raise ValueError("cleanup minimum confidence must be between 0 and 1")
    if not 0 <= config.min_duration_seconds <= 1:
        raise ValueError("cleanup minimum duration must be between 0 and 1 second")
    if not 0 <= config.adjacent_same_pitch_gap_seconds <= 0.1:
        raise ValueError("cleanup adjacent same-pitch gap must be between 0 and 0.1 seconds")
    if not 1 <= config.max_note_duration_seconds <= 90:
        raise ValueError("cleanup maximum note duration must be between 1 and 90 seconds")


def _valid_event(event: NoteEvent) -> bool:
    return (
        all(math.isfinite(value) for value in (event.start_sec, event.end_sec, event.confidence))
        and event.start_sec >= 0
        and event.end_sec > event.start_sec
        and 0 <= event.pitch <= 127
        and 1 <= event.velocity <= 127
        and 0 <= event.confidence <= 1
    )


def _winner_key(event: NoteEvent) -> tuple[float, float, int, float, float, str]:
    return (
        event.confidence,
        event.end_sec - event.start_sec,
        event.velocity,
        -event.start_sec,
        -event.end_sec,
        event.hand or "",
    )


def _event_sort_key(event: NoteEvent) -> tuple[float, int, float, float, int, str]:
    return (
        event.start_sec,
        event.pitch,
        event.end_sec,
        -event.confidence,
        -event.velocity,
        event.hand or "",
    )
