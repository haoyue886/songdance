from dataclasses import replace

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.transcribe import NoteEvent

GRID_DIVISIONS = 4


def quantize_events(
    events: list[NoteEvent], analysis: StructureAnalysis
) -> list[NoteEvent]:
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
                hand=None,
                hand_confidence=None,
            )
        )
    return sorted(quantized, key=lambda item: (item.start_sec, item.pitch, item.end_sec))


def seconds_per_quarter(analysis: StructureAnalysis) -> float:
    return 60.0 / analysis.bpm


def notation_measure_offset_units(analysis: StructureAnalysis) -> int:
    if not analysis.downbeat_grid_seconds:
        return 0
    measure_units = {"3/4": 12, "4/4": 16, "6/8": 12}[analysis.time_signature]
    downbeat_units = round(
        analysis.downbeat_grid_seconds[0]
        / seconds_per_quarter(analysis)
        * GRID_DIVISIONS
    )
    return (-downbeat_units) % measure_units


def _subdivision_grid(
    events: list[NoteEvent], analysis: StructureAnalysis
) -> tuple[float, ...]:
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
