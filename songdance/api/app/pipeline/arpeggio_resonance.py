from dataclasses import dataclass

from app.pipeline.simple_arpeggio import (
    SIMPLE_ARPEGGIO_PATTERN,
    _has_explicit_crossing,
    _RepeatedCycleMatch,
    _stable_repeated_cycle_match,
    _trailing_pattern_slot_indexes,
)
from app.pipeline.transcribe import NoteEvent

SIMPLE_ARPEGGIO_FILTER_VERSION = "simple-arpeggio-filter-v3"
SIMPLE_ARPEGGIO_RESONANCE_FILTERED = "SIMPLE_ARPEGGIO_RESONANCE_FILTERED"
MINIMUM_PEDAL_CYCLES = 3
MINIMUM_CYCLE_PEDAL_COVERAGE = 0.5
MINIMUM_PARALLEL_SLOT_RUN = 3
MINIMUM_PARALLEL_PITCH_SEPARATION = 5


@dataclass(frozen=True)
class ArpeggioFilterResult:
    events: list[NoteEvent]
    version: str
    applied: bool
    removed_event_count: int
    stable_cycle_count: int
    matched_slot_count: int
    reason_codes: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "applied": self.applied,
            "removed_event_count": self.removed_event_count,
            "stable_cycle_count": self.stable_cycle_count,
            "matched_slot_count": self.matched_slot_count,
            "reason_codes": self.reason_codes,
        }


def filter_simple_arpeggio_resonance(
    events: list[NoteEvent], *, pedal_intervals: tuple[tuple[float, float], ...]
) -> ArpeggioFilterResult:
    match = _stable_repeated_cycle_match(events)
    if match is None:
        return _filter_result(events)
    supported_cycles = _supported_cycle_indexes(match, pedal_intervals)
    if len(supported_cycles) < MINIMUM_PEDAL_CYCLES:
        return _filter_result(events)
    supported_ranges = tuple(match.ranges[index] for index in supported_cycles)
    if _has_explicit_crossing(events, supported_ranges):
        return _filter_result(events)

    slot_by_group = {
        group_index: slot
        for cycle_index in supported_cycles
        for slot, group_index in enumerate(match.cycles[cycle_index])
    }
    if supported_cycles[-1] == len(match.cycles) - 1:
        slot_by_group.update(_trailing_pattern_slot_indexes(match))
    expected_by_group = {
        group_index: SIMPLE_ARPEGGIO_PATTERN[slot] for group_index, slot in slot_by_group.items()
    }
    parallel_events = _stable_parallel_event_ids(match, supported_cycles, slot_by_group)
    pattern_pitches = set(SIMPLE_ARPEGGIO_PATTERN)
    removed_ids: set[int] = set()
    for group_index, (_, group) in enumerate(match.groups):
        expected_pitch = expected_by_group.get(group_index)
        if expected_pitch is None:
            continue
        candidates = [event for event in group if event.pitch == expected_pitch]
        if not candidates:
            continue
        selected = max(
            candidates,
            key=lambda event: (
                event.confidence,
                event.velocity,
                event.end_sec - event.start_sec,
            ),
        )
        for event in group:
            if (
                event is selected
                or id(event) in parallel_events
                or event.pitch not in pattern_pitches
                or _is_independent_pattern_voice(event, expected_by_group, match.groups)
            ):
                continue
            removed_ids.add(id(event))
    return _filter_result(
        [event for event in events if id(event) not in removed_ids],
        len(removed_ids),
        stable_cycle_count=len(supported_cycles),
        matched_slot_count=len(expected_by_group),
    )


def _supported_cycle_indexes(
    match: _RepeatedCycleMatch, pedal_intervals: tuple[tuple[float, float], ...]
) -> tuple[int, ...]:
    intervals = _merge_intervals(pedal_intervals)
    covered = [
        _coverage_ratio(cycle_range, intervals) >= MINIMUM_CYCLE_PEDAL_COVERAGE
        for cycle_range in match.ranges
    ]
    supported = []
    start = 0
    while start < len(covered):
        if not covered[start]:
            start += 1
            continue
        end = start + 1
        while end < len(covered) and covered[end]:
            end += 1
        if end - start >= MINIMUM_PEDAL_CYCLES:
            supported.extend(range(start, end))
        start = end
    return tuple(supported)


def _coverage_ratio(
    cycle_range: tuple[float, float], intervals: tuple[tuple[float, float], ...]
) -> float:
    start, end = cycle_range
    duration = end - start
    if duration <= 0:
        return 0.0
    covered = sum(
        max(0.0, min(end, interval_end) - max(start, interval_start))
        for interval_start, interval_end in intervals
    )
    return min(1.0, covered / duration)


def _stable_parallel_event_ids(
    match: _RepeatedCycleMatch,
    supported_cycles: tuple[int, ...],
    slot_by_group: dict[int, int],
) -> set[int]:
    pattern_pitches = set(SIMPLE_ARPEGGIO_PATTERN)
    parallel_by_slot: dict[int, set[int]] = {}
    sustained_slots: set[int] = set()
    for slot, expected_pitch in enumerate(SIMPLE_ARPEGGIO_PATTERN):
        pitch_sets = []
        for cycle_index in supported_cycles:
            group_index = match.cycles[cycle_index][slot]
            pitch_sets.append(
                {
                    event.pitch
                    for event in match.groups[group_index][1]
                    if event.pitch in pattern_pitches
                    and event.pitch != expected_pitch
                    and abs(event.pitch - expected_pitch) >= MINIMUM_PARALLEL_PITCH_SEPARATION
                }
            )
        common = set.intersection(*pitch_sets) if pitch_sets else set()
        if common:
            parallel_by_slot[slot] = common
        if any(
            all(
                any(
                    event.pitch == pitch
                    and event.end_sec >= match.groups[group_index][0] + match.step_seconds * 0.8
                    for event in match.groups[group_index][1]
                )
                for cycle_index in supported_cycles
                for group_index in (match.cycles[cycle_index][slot],)
            )
            for pitch in common
        ):
            sustained_slots.add(slot)

    if len(parallel_by_slot) == len(SIMPLE_ARPEGGIO_PATTERN):
        protected_slots = set(parallel_by_slot)
    else:
        protected_slots = _cyclic_run_slots(
            sustained_slots,
            len(SIMPLE_ARPEGGIO_PATTERN),
            MINIMUM_PARALLEL_SLOT_RUN,
        )
    return {
        id(event)
        for group_index, slot in slot_by_group.items()
        for event in match.groups[group_index][1]
        if slot in protected_slots and event.pitch in parallel_by_slot[slot]
    }


def _cyclic_run_slots(slots: set[int], cycle_length: int, minimum: int) -> set[int]:
    protected: set[int] = set()
    for start in range(cycle_length):
        run = []
        for offset in range(cycle_length):
            slot = (start + offset) % cycle_length
            if slot not in slots:
                break
            run.append(slot)
        if len(run) >= minimum:
            protected.update(run)
    return protected


def _is_independent_pattern_voice(
    event: NoteEvent,
    expected_by_group: dict[int, int],
    groups: tuple[tuple[float, tuple[NoteEvent, ...]], ...],
) -> bool:
    separated_slots = sum(
        event.start_sec < groups[index][0] < event.end_sec
        and abs(event.pitch - expected_pitch) >= 5
        for index, expected_pitch in expected_by_group.items()
    )
    return separated_slots >= 3


def _merge_intervals(intervals: tuple[tuple[float, float], ...]) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _filter_result(
    events: list[NoteEvent],
    removed: int = 0,
    *,
    stable_cycle_count: int = 0,
    matched_slot_count: int = 0,
) -> ArpeggioFilterResult:
    return ArpeggioFilterResult(
        events=events,
        version=SIMPLE_ARPEGGIO_FILTER_VERSION,
        applied=removed > 0,
        removed_event_count=removed,
        stable_cycle_count=stable_cycle_count,
        matched_slot_count=matched_slot_count,
        reason_codes=(SIMPLE_ARPEGGIO_RESONANCE_FILTERED,) if removed else (),
    )
