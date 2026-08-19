from dataclasses import asdict, dataclass

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.transcribe import NoteEvent

ADAPTIVE_QUANTIZATION_VERSION = "adaptive-quantization-v1"
DEFAULT_DIVISIONS_PER_QUARTER = 4
SUPPORTED_DIVISIONS_PER_QUARTER = (4, 8, 16)
REFERENCE_QUANTIZATION_CONTEXT = "REFERENCE_QUANTIZATION_CONTEXT"
SHORT_VALUE_EVIDENCE = "SHORT_VALUE_EVIDENCE"
DEFAULT_SIXTEENTH_GRID = "DEFAULT_SIXTEENTH_GRID"


@dataclass(frozen=True)
class QuantizationDecision:
    version: str
    divisions_per_quarter: int
    shortest_note_value: int
    source: str
    reason_codes: tuple[str, ...]
    adjacent_interval_count: int
    matched_interval_count: int
    phase_alignment_ratio: float
    coarse_offgrid_ratio: float
    measure_units: int

    def summary(self) -> dict[str, object]:
        return asdict(self)


def select_quantization(
    events: list[NoteEvent],
    analysis: StructureAnalysis,
    *,
    forced_divisions_per_quarter: int | None = None,
    source: str | None = None,
) -> QuantizationDecision:
    if forced_divisions_per_quarter is not None:
        if forced_divisions_per_quarter not in SUPPORTED_DIVISIONS_PER_QUARTER:
            raise ValueError("quantization divisions must be one of 4, 8, or 16")
        return _decision(
            analysis,
            forced_divisions_per_quarter,
            source or "reference_score",
            (REFERENCE_QUANTIZATION_CONTEXT,),
        )

    quarter_seconds = 60.0 / analysis.bpm
    onsets = _clustered_onsets(events, quarter_seconds)
    gaps = [right - left for left, right in zip(onsets, onsets[1:], strict=False)]
    anchor = next(
        iter(analysis.downbeat_grid_seconds or analysis.beat_grid_seconds),
        onsets[0] if onsets else 0.0,
    )
    for divisions in (16, 8):
        evidence = _candidate_evidence(onsets, gaps, quarter_seconds, anchor, divisions)
        if evidence is not None:
            return _decision(
                analysis,
                divisions,
                "audio_onset_pattern",
                (SHORT_VALUE_EVIDENCE,),
                adjacent_interval_count=len(gaps),
                **evidence,
            )
    return _decision(
        analysis,
        DEFAULT_DIVISIONS_PER_QUARTER,
        "conservative_default",
        (DEFAULT_SIXTEENTH_GRID,),
        adjacent_interval_count=len(gaps),
    )


def _candidate_evidence(
    onsets: list[float],
    gaps: list[float],
    quarter_seconds: float,
    anchor: float,
    divisions: int,
) -> dict[str, int | float] | None:
    step = quarter_seconds / divisions
    matching = [gap for gap in gaps if step * 0.65 <= gap <= step * 1.35]
    phase_ratio = _ratio(
        sum(_grid_distance(onset, anchor, step) <= step * 0.22 for onset in onsets),
        len(onsets),
    )
    coarse_step = step * 2
    offgrid_ratio = _ratio(
        sum(_grid_distance(onset, anchor, coarse_step) >= step * 0.7 for onset in onsets),
        len(onsets),
    )
    matching_ratio = _ratio(len(matching), len(gaps))
    if len(matching) < 7 or matching_ratio < 0.25 or phase_ratio < 0.75 or offgrid_ratio < 0.2:
        return None
    return {
        "matched_interval_count": len(matching),
        "phase_alignment_ratio": phase_ratio,
        "coarse_offgrid_ratio": offgrid_ratio,
    }


def _clustered_onsets(events: list[NoteEvent], quarter_seconds: float) -> list[float]:
    tolerance = quarter_seconds / 32
    clusters: list[list[float]] = []
    for onset in sorted({event.start_sec for event in events}):
        if clusters and onset - clusters[-1][-1] <= tolerance:
            clusters[-1].append(onset)
        else:
            clusters.append([onset])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def _grid_distance(value: float, anchor: float, step: float) -> float:
    units = round((value - anchor) / step)
    return abs(value - (anchor + units * step))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _decision(
    analysis: StructureAnalysis,
    divisions: int,
    source: str,
    reasons: tuple[str, ...],
    *,
    adjacent_interval_count: int = 0,
    matched_interval_count: int = 0,
    phase_alignment_ratio: float = 0.0,
    coarse_offgrid_ratio: float = 0.0,
) -> QuantizationDecision:
    numerator, denominator = map(int, analysis.time_signature.split("/", 1))
    measure_quarters = numerator * 4 / denominator
    measure_units = round(measure_quarters * divisions)
    if measure_units / divisions != measure_quarters:
        raise ValueError("quantization grid must conserve complete measure duration")
    return QuantizationDecision(
        version=ADAPTIVE_QUANTIZATION_VERSION,
        divisions_per_quarter=divisions,
        shortest_note_value=divisions * 4,
        source=source,
        reason_codes=reasons,
        adjacent_interval_count=adjacent_interval_count,
        matched_interval_count=matched_interval_count,
        phase_alignment_ratio=phase_alignment_ratio,
        coarse_offgrid_ratio=coarse_offgrid_ratio,
        measure_units=measure_units,
    )
