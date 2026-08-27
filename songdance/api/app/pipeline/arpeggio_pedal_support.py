from app.pipeline.simple_arpeggio import _RepeatedCycleMatch

MINIMUM_PEDAL_CYCLES = 3
MINIMUM_CYCLE_PEDAL_COVERAGE = 0.5


def supported_cycle_indexes(
    match: _RepeatedCycleMatch,
    pedal_intervals: tuple[tuple[float, float], ...],
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


def _merge_intervals(
    intervals: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)
