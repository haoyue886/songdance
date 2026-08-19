from dataclasses import dataclass, replace
from statistics import median

from app.pipeline.transcribe import NoteEvent

SIMPLE_ARPEGGIO_APPLIED = "SIMPLE_ARPEGGIO_APPLIED"
SIMPLE_ARPEGGIO_REJECTED_CROSSING = "SIMPLE_ARPEGGIO_REJECTED_CROSSING"
SIMPLE_ARPEGGIO_STABLE_TIMING = "SIMPLE_ARPEGGIO_STABLE_TIMING"
SIMPLE_ARPEGGIO_CLEAR_ZONE = "SIMPLE_ARPEGGIO_CLEAR_ZONE"
SIMPLE_ARPEGGIO_PATTERN = (48, 55, 60, 64, 67, 72, 67, 64)
SIMPLE_ARPEGGIO_LEFT_MAX = 60
SIMPLE_ARPEGGIO_RIGHT_MIN = 64
SIMPLE_ARPEGGIO_RIGHT_HAND_MIN = 60
SIMPLE_ARPEGGIO_CONFIDENCE = 0.92


@dataclass(frozen=True)
class _RepeatedCycleMatch:
    groups: tuple[tuple[float, tuple[NoteEvent, ...]], ...]
    cycles: tuple[tuple[int, ...], ...]
    ranges: tuple[tuple[float, float], ...]
    step_seconds: float


def apply_simple_arpeggio_strategy(
    assigned: list[NoteEvent], source_events: list[NoteEvent]
) -> tuple[list[NoteEvent], str, tuple[str, ...]]:
    ordered = sorted(assigned, key=lambda item: (item.start_sec, item.pitch, item.end_sec))
    ranges = _stable_single_cycle_ranges(ordered) or _stable_repeated_cycle_ranges(ordered)
    if not ranges:
        return assigned, "continuity", ()
    if _has_explicit_crossing(source_events, ranges):
        return assigned, "continuity", (SIMPLE_ARPEGGIO_REJECTED_CROSSING,)

    stabilized = [
        _assign_clear_zone(event) if _in_ranges(event.start_sec, ranges) else event
        for event in assigned
    ]
    return (
        stabilized,
        "simple_arpeggio_stable_zone",
        (
            SIMPLE_ARPEGGIO_APPLIED,
            SIMPLE_ARPEGGIO_STABLE_TIMING,
            SIMPLE_ARPEGGIO_CLEAR_ZONE,
        ),
    )


def _has_explicit_crossing(
    events: list[NoteEvent], ranges: tuple[tuple[float, float], ...]
) -> bool:
    return any(
        _in_ranges(event.start_sec, ranges)
        and (event.hand_confidence is None or event.hand_confidence >= SIMPLE_ARPEGGIO_CONFIDENCE)
        and (
            (event.hand == "right" and event.pitch < SIMPLE_ARPEGGIO_RIGHT_HAND_MIN)
            or (event.hand == "left" and event.pitch >= SIMPLE_ARPEGGIO_RIGHT_MIN)
        )
        for event in events
    )


def _stable_single_cycle_ranges(
    events: list[NoteEvent],
) -> tuple[tuple[float, float], ...]:
    if len(events) != len(SIMPLE_ARPEGGIO_PATTERN):
        return ()
    if tuple(event.pitch for event in events) != SIMPLE_ARPEGGIO_PATTERN:
        return ()
    deltas = tuple(
        right.start_sec - left.start_sec for left, right in zip(events, events[1:], strict=False)
    )
    if not _is_stable_period(deltas, minimum_period=0.03, relative_tolerance=0.25):
        return ()
    return ((events[0].start_sec, events[-1].end_sec),)


def _stable_repeated_cycle_ranges(
    events: list[NoteEvent],
) -> tuple[tuple[float, float], ...]:
    match = _stable_repeated_cycle_match(events)
    return match.ranges if match is not None else ()


def _stable_repeated_cycle_match(
    events: list[NoteEvent],
) -> _RepeatedCycleMatch | None:
    onset_groups = _group_by_onset(events)
    cycles: list[tuple[float, ...]] = []
    cycle_indexes: list[tuple[int, ...]] = []
    cursor = 0
    while cursor < len(onset_groups):
        cycle = _match_cycle(onset_groups, cursor)
        if cycle is None:
            cursor += 1
            continue
        cycles.append(tuple(onset_groups[index][0] for index in cycle))
        cycle_indexes.append(cycle)
        cursor = cycle[-1] + 1

    if len(cycles) < 3:
        return None
    cycle_periods = tuple(
        right[0] - left[0] for left, right in zip(cycles, cycles[1:], strict=False)
    )
    if not _is_stable_period(cycle_periods, minimum_period=0.25, relative_tolerance=0.2):
        return None
    matched_onsets = tuple(onset for cycle in cycles for onset in cycle)
    note_steps = tuple(
        right - left for left, right in zip(matched_onsets, matched_onsets[1:], strict=False)
    )
    if not _is_stable_period(note_steps, minimum_period=0.03, relative_tolerance=0.25):
        return None
    final_end = cycles[-1][-1] + median(note_steps)
    ranges = tuple(
        (cycle[0], cycles[index + 1][0] if index + 1 < len(cycles) else final_end)
        for index, cycle in enumerate(cycles)
    )
    match = _RepeatedCycleMatch(
        groups=tuple(onset_groups),
        cycles=tuple(cycle_indexes),
        ranges=ranges,
        step_seconds=median(note_steps),
    )
    trailing = _trailing_pattern_slot_indexes(match)
    if trailing:
        last_onset = match.groups[max(trailing)][0]
        match = replace(
            match,
            ranges=(*match.ranges[:-1], (match.ranges[-1][0], last_onset + match.step_seconds)),
        )
    return match


def _trailing_pattern_slots(match: _RepeatedCycleMatch) -> dict[int, int]:
    return {
        group_index: SIMPLE_ARPEGGIO_PATTERN[slot]
        for group_index, slot in _trailing_pattern_slot_indexes(match).items()
    }


def _trailing_pattern_slot_indexes(match: _RepeatedCycleMatch) -> dict[int, int]:
    slots = {}
    cursor = match.cycles[-1][-1]
    expected_time = match.groups[cursor][0] + match.step_seconds
    tolerance = max(0.03, match.step_seconds * 0.25)
    for slot, pitch in enumerate(SIMPLE_ARPEGGIO_PATTERN):
        next_index = next(
            (
                index
                for index in range(cursor + 1, min(len(match.groups), cursor + 5))
                if _group_has_pitch(match.groups[index], pitch)
                and abs(match.groups[index][0] - expected_time) <= tolerance
            ),
            None,
        )
        if next_index is None:
            break
        slots[next_index] = slot
        cursor = next_index
        expected_time = match.groups[cursor][0] + match.step_seconds
    return slots


def _group_by_onset(events: list[NoteEvent]) -> list[tuple[float, tuple[NoteEvent, ...]]]:
    grouped: dict[float, list[NoteEvent]] = {}
    for event in events:
        grouped.setdefault(event.start_sec, []).append(event)
    return [
        (onset, tuple(sorted(items, key=lambda item: (item.pitch, item.end_sec))))
        for onset, items in sorted(grouped.items())
    ]


def _match_cycle(
    groups: list[tuple[float, tuple[NoteEvent, ...]]], start: int
) -> tuple[int, ...] | None:
    if not _group_has_pitch(groups[start], SIMPLE_ARPEGGIO_PATTERN[0]):
        return None
    matched = [start]
    cursor = start
    for pitch in SIMPLE_ARPEGGIO_PATTERN[1:]:
        next_index = next(
            (
                index
                for index in range(cursor + 1, min(len(groups), cursor + 5))
                if _group_has_pitch(groups[index], pitch)
                and groups[index][0] - groups[cursor][0] <= 0.75
            ),
            None,
        )
        if next_index is None:
            return None
        matched.append(next_index)
        cursor = next_index
    return tuple(matched)


def _group_has_pitch(group: tuple[float, tuple[NoteEvent, ...]], pitch: int) -> bool:
    return any(event.pitch == pitch for event in group[1])


def _is_stable_period(
    deltas: tuple[float, ...], minimum_period: float, relative_tolerance: float
) -> bool:
    if not deltas:
        return False
    center = median(deltas)
    tolerance = max(0.03, center * relative_tolerance)
    return center >= minimum_period and all(abs(delta - center) <= tolerance for delta in deltas)


def _in_ranges(position: float, ranges: tuple[tuple[float, float], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _assign_clear_zone(event: NoteEvent) -> NoteEvent:
    if event.pitch < SIMPLE_ARPEGGIO_RIGHT_HAND_MIN:
        hand = "left"
    else:
        hand = "right"
    confidence = max(event.hand_confidence or 0.0, SIMPLE_ARPEGGIO_CONFIDENCE)
    return replace(event, hand=hand, hand_confidence=round(confidence, 6))
