from dataclasses import asdict, dataclass, replace
from statistics import median

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.transcribe import NoteEvent

GRID_DIVISIONS = 4
FALSE_PICKUP_REJECTED_FULL_MEASURE = "FALSE_PICKUP_REJECTED_FULL_MEASURE"


@dataclass(frozen=True)
class PickupDecision:
    measure_offset_units: int
    applied: bool
    reason_codes: tuple[str, ...]
    candidate_pickup_units: int
    first_measure_occupied_slots: int
    complete_cycle_count: int
    matching_complete_cycles: int
    cycle_match_ratio: float
    first_onset_velocity: int
    candidate_downbeat_velocity: int

    def summary(self) -> dict[str, object]:
        return asdict(self)


def quantize_events(events: list[NoteEvent], analysis: StructureAnalysis) -> list[NoteEvent]:
    grid = _subdivision_grid(events, analysis)
    quantized = []
    for event in events:
        start = _nearest(grid, event.start_sec)
        end = _nearest(grid, event.end_sec)
        if end <= start:
            end = _next_grid_value(grid, start)
        quantized.append(
            replace(
                event,
                start_sec=round(start, 6),
                end_sec=round(end, 6),
            )
        )
    return sorted(quantized, key=lambda item: (item.start_sec, item.pitch, item.end_sec))


def align_repeating_eighth_note_cycles(
    events: list[NoteEvent],
    analysis: StructureAnalysis,
    pickup: PickupDecision,
) -> list[NoteEvent]:
    if FALSE_PICKUP_REJECTED_FULL_MEASURE not in pickup.reason_codes:
        return events

    notation_eighth = seconds_per_quarter(analysis) / 2
    observed_eighth = _observed_eighth_seconds(events, notation_eighth)
    origin = min(event.start_sec for event in events)
    aligned = []
    for event in events:
        start_slot = max(0, round((event.start_sec - origin) / observed_eighth))
        duration_slots = max(1, round((event.end_sec - event.start_sec) / observed_eighth))
        start = start_slot * notation_eighth
        aligned.append(
            replace(
                event,
                start_sec=round(start, 6),
                end_sec=round(start + duration_slots * notation_eighth, 6),
            )
        )
    return sorted(aligned, key=lambda item: (item.start_sec, item.pitch, item.end_sec))


def _observed_eighth_seconds(events: list[NoteEvent], expected: float) -> float:
    starts = sorted({event.start_sec for event in events})
    clusters: list[list[float]] = []
    for start in starts:
        if clusters and start - clusters[-1][-1] <= expected * 0.25:
            clusters[-1].append(start)
        else:
            clusters.append([start])
    centers = [median(cluster) for cluster in clusters]
    candidates = [
        right - left
        for left, right in zip(centers, centers[1:], strict=False)
        if expected * 0.6 <= right - left <= expected * 1.4
    ]
    return median(candidates) if len(candidates) >= 7 else expected


def seconds_per_quarter(analysis: StructureAnalysis) -> float:
    return 60.0 / analysis.bpm


def notation_measure_offset_units(analysis: StructureAnalysis) -> int:
    if not analysis.downbeat_grid_seconds:
        return 0
    measure_units = _measure_units(analysis)
    downbeat_units = round(
        analysis.downbeat_grid_seconds[0] / seconds_per_quarter(analysis) * GRID_DIVISIONS
    )
    return (-downbeat_units) % measure_units


def decide_notation_pickup(events: list[NoteEvent], analysis: StructureAnalysis) -> PickupDecision:
    offset_units = notation_measure_offset_units(analysis)
    measure_units = _measure_units(analysis)
    candidate_units = measure_units - offset_units if offset_units else 0
    evidence = _complete_eighth_note_measure_evidence(events, analysis, candidate_units)
    if evidence is not None:
        return PickupDecision(
            measure_offset_units=0,
            applied=False,
            reason_codes=(FALSE_PICKUP_REJECTED_FULL_MEASURE,),
            candidate_pickup_units=candidate_units,
            **evidence,
        )
    return PickupDecision(
        measure_offset_units=offset_units,
        applied=offset_units > 0,
        reason_codes=(),
        candidate_pickup_units=candidate_units,
        first_measure_occupied_slots=0,
        complete_cycle_count=0,
        matching_complete_cycles=0,
        cycle_match_ratio=0.0,
        first_onset_velocity=0,
        candidate_downbeat_velocity=0,
    )


def _complete_eighth_note_measure_evidence(
    events: list[NoteEvent], analysis: StructureAnalysis, candidate_units: int
) -> dict[str, int | float] | None:
    if (
        analysis.time_signature != "4/4"
        or candidate_units != GRID_DIVISIONS // 2
        or not events
        or not analysis.downbeat_grid_seconds
    ):
        return None

    first_onset = min(event.start_sec for event in events)
    candidate_downbeat = analysis.downbeat_grid_seconds[0]
    eighth_seconds = candidate_downbeat - first_onset
    expected_eighth = seconds_per_quarter(analysis) / 2
    if eighth_seconds <= 0 or abs(eighth_seconds - expected_eighth) > expected_eighth * 0.2:
        return None

    first_velocity = _onset_velocity(events, first_onset, eighth_seconds * 0.2)
    downbeat_velocity = _onset_velocity(events, candidate_downbeat, eighth_seconds * 0.2)
    first_slots = _occupied_slots(
        events, first_onset, eighth_seconds, start_slot=0, slot_count=8, tolerance=0.55
    )
    complete_cycle_count = _complete_cycle_count(events, first_onset, eighth_seconds)
    matching_cycles = sum(
        _occupied_slots(
            events,
            first_onset,
            eighth_seconds,
            start_slot=cycle * 8,
            slot_count=8,
            tolerance=0.55,
        )
        == 8
        for cycle in range(complete_cycle_count)
    )
    cycle_match_ratio = matching_cycles / complete_cycle_count if complete_cycle_count else 0.0
    if (
        first_slots < 8
        or complete_cycle_count < 3
        or cycle_match_ratio < 0.8
        or first_velocity < downbeat_velocity
    ):
        return None
    return {
        "first_measure_occupied_slots": first_slots,
        "complete_cycle_count": complete_cycle_count,
        "matching_complete_cycles": matching_cycles,
        "cycle_match_ratio": round(cycle_match_ratio, 6),
        "first_onset_velocity": first_velocity,
        "candidate_downbeat_velocity": downbeat_velocity,
    }


def _measure_units(analysis: StructureAnalysis) -> int:
    return {"3/4": 12, "4/4": 16, "6/8": 12}[analysis.time_signature]


def _onset_velocity(events: list[NoteEvent], target: float, tolerance: float) -> int:
    return max(
        (event.velocity for event in events if abs(event.start_sec - target) <= tolerance),
        default=0,
    )


def _occupied_slots(
    events: list[NoteEvent],
    origin: float,
    interval: float,
    *,
    start_slot: int,
    slot_count: int,
    tolerance: float,
) -> int:
    starts = sorted({event.start_sec for event in events})
    start_index = 0
    matched = 0
    for slot in range(start_slot, start_slot + slot_count):
        target = origin + slot * interval
        lower_bound = target - interval * tolerance
        upper_bound = target + interval * tolerance
        while start_index < len(starts) and starts[start_index] < lower_bound:
            start_index += 1
        if start_index < len(starts) and starts[start_index] <= upper_bound:
            matched += 1
            start_index += 1
    return matched


def _complete_cycle_count(events: list[NoteEvent], origin: float, interval: float) -> int:
    last_onset = max(event.start_sec for event in events)
    occupied_span_in_slots = (last_onset - origin) / interval + 1
    return max(0, int((occupied_span_in_slots + 0.55) // 8))


def _subdivision_grid(events: list[NoteEvent], analysis: StructureAnalysis) -> tuple[float, ...]:
    end = max((event.end_sec for event in events), default=0.0)
    beat_grid = analysis.beat_grid_seconds
    anchor_grid = analysis.downbeat_grid_seconds or beat_grid
    interval = seconds_per_quarter(analysis)
    anchor = anchor_grid[0] if anchor_grid else 0.0
    if len(beat_grid) >= 2:
        intervals = [right - left for left, right in zip(beat_grid, beat_grid[1:], strict=False)]
        positive = sorted(value for value in intervals if value > 0)
        if positive:
            interval = positive[len(positive) // 2]
    step = interval / GRID_DIVISIONS
    start_index = int((0.0 - anchor) // step) - 1
    end_index = int((end - anchor) // step) + 2
    return tuple(anchor + index * step for index in range(start_index, end_index + 1))


def _nearest(grid: tuple[float, ...], value: float) -> float:
    return min(grid, key=lambda candidate: (abs(candidate - value), candidate))


def _next_grid_value(grid: tuple[float, ...], value: float) -> float:
    return next(candidate for candidate in grid if candidate > value)
