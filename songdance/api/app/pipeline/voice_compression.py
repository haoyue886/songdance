import hashlib
import json
from dataclasses import asdict, dataclass, replace

from app.pipeline.harmony import NotationGroup
from app.pipeline.quantize import GRID_DIVISIONS
from app.pipeline.sustain import SUSTAIN_EVIDENCE_UNAVAILABLE, SustainEvidence

VOICE_COMPRESSION_VERSION = "voice-compression-v1"
DENSE_RESONANT_ONSETS_COMPRESSED = "DENSE_RESONANT_ONSETS_COMPRESSED"


@dataclass(frozen=True)
class VoiceCompressionConfig:
    minimum_run_onsets: int = 8
    maximum_dense_gap_units: int = GRID_DIVISIONS // 2
    onset_tolerance_units: int = 1
    maximum_chord_size: int = 4
    minimum_independent_overlap_onsets: int = 3
    minimum_independent_pitch_separation: int = 5

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{VOICE_COMPRESSION_VERSION}/{digest}"


@dataclass(frozen=True)
class VoiceCompressionResult:
    groups: list[NotationGroup]
    version: str
    applied: bool
    compressed_group_count: int
    coalesced_group_count: int
    dense_run_count: int
    reason_codes: tuple[str, ...]
    evidence: SustainEvidence

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "applied": self.applied,
            "compressed_group_count": self.compressed_group_count,
            "coalesced_group_count": self.coalesced_group_count,
            "dense_run_count": self.dense_run_count,
            "reason_codes": self.reason_codes,
            "evidence": self.evidence.summary(),
            "pedal_marking_applied": False,
        }


def compress_notation_durations(
    groups: list[NotationGroup],
    seconds_per_quarter: float,
    measure_offset_units: int,
    evidence: SustainEvidence | None,
    config: VoiceCompressionConfig | None = None,
) -> VoiceCompressionResult:
    active = config or VoiceCompressionConfig()
    available = evidence or SustainEvidence.unavailable()
    if not groups or available.status != "available":
        return VoiceCompressionResult(
            groups=groups,
            version=active.version,
            applied=False,
            compressed_group_count=0,
            coalesced_group_count=0,
            dense_run_count=0,
            reason_codes=(SUSTAIN_EVIDENCE_UNAVAILABLE,),
            evidence=available,
        )

    onset_units = _to_units(
        available.independent_onset_seconds, seconds_per_quarter, measure_offset_units
    )
    interval_units = tuple(
        (
            _to_unit(left, seconds_per_quarter, measure_offset_units),
            _to_unit(right, seconds_per_quarter, measure_offset_units),
        )
        for left, right in (*available.resonant_intervals, *available.cc64_intervals)
    )
    supported_starts = [
        start
        for start in sorted({group.start_units for group in groups})
        if any(abs(start - onset) <= active.onset_tolerance_units for onset in onset_units)
    ]
    runs = [
        run
        for run in _dense_runs(supported_starts, active)
        if all(
            _interval_supported(left, right, interval_units, active.onset_tolerance_units)
            for left, right in zip(run, run[1:], strict=False)
        )
    ]
    next_start = {
        start: following for run in runs for start, following in zip(run, run[1:], strict=False)
    }
    run_by_start = {start: run for run in runs for start in run[:-1]}
    groups_by_start: dict[int, list[NotationGroup]] = {}
    for group in groups:
        groups_by_start.setdefault(group.start_units, []).append(group)
    pitch_retriggers = _pitch_retriggers(groups)
    compressed = []
    count = 0
    for group in groups:
        end_units = next_start.get(group.start_units)
        run = run_by_start.get(group.start_units, [])
        independent_pitches = tuple(
            pitch
            for pitch in group.pitches
            if _has_independent_voice_evidence(
                group,
                pitch,
                run,
                groups_by_start,
                pitch_retriggers.get((group.start_units, pitch)),
                active.minimum_independent_overlap_onsets,
                active.minimum_independent_pitch_separation,
            )
        )
        compressible_pitches = tuple(
            pitch for pitch in group.pitches if pitch not in independent_pitches
        )
        if end_units is not None and group.end_units > end_units and compressible_pitches:
            if independent_pitches:
                compressed.append(replace(group, pitches=independent_pitches))
            compressed.append(
                replace(group, end_units=end_units, pitches=compressible_pitches)
            )
            count += 1
        else:
            compressed.append(group)
    coalesced = _coalesce_onsets(compressed, set(next_start), active.maximum_chord_size)
    return VoiceCompressionResult(
        groups=coalesced,
        version=active.version,
        applied=count > 0,
        compressed_group_count=count,
        coalesced_group_count=len(compressed) - len(coalesced),
        dense_run_count=len(runs),
        reason_codes=(DENSE_RESONANT_ONSETS_COMPRESSED,) if count else (),
        evidence=available,
    )


def _pitch_retriggers(
    groups: list[NotationGroup],
) -> dict[tuple[int, int], int]:
    starts_by_pitch: dict[int, list[int]] = {}
    for group in groups:
        for pitch in group.pitches:
            starts_by_pitch.setdefault(pitch, []).append(group.start_units)
    retriggers = {}
    for pitch, starts in starts_by_pitch.items():
        ordered = sorted(set(starts))
        retriggers.update(
            {
                (start, pitch): following
                for start, following in zip(ordered, ordered[1:], strict=False)
            }
        )
    return retriggers


def _has_independent_voice_evidence(
    group: NotationGroup,
    pitch: int,
    run: list[int],
    groups_by_start: dict[int, list[NotationGroup]],
    same_pitch_retrigger: int | None,
    minimum_overlap_onsets: int,
    minimum_pitch_separation: int,
) -> bool:
    if run and same_pitch_retrigger is not None and same_pitch_retrigger <= run[-1]:
        return False
    effective_end = min(group.end_units, same_pitch_retrigger or group.end_units)
    overlapped = [onset for onset in run if group.start_units < onset < effective_end]
    separated = 0
    for onset in overlapped:
        other_pitches = [
            pitch for candidate in groups_by_start.get(onset, []) for pitch in candidate.pitches
        ]
        if other_pitches and all(
            abs(pitch - other) >= minimum_pitch_separation for other in other_pitches
        ):
            separated += 1
    return separated >= minimum_overlap_onsets


def _to_units(
    seconds: tuple[float, ...], seconds_per_quarter: float, offset: int
) -> tuple[int, ...]:
    return tuple(sorted({_to_unit(value, seconds_per_quarter, offset) for value in seconds}))


def _to_unit(value: float, seconds_per_quarter: float, offset: int) -> int:
    return round(value / seconds_per_quarter * GRID_DIVISIONS) + offset


def _dense_runs(starts: list[int], config: VoiceCompressionConfig) -> list[list[int]]:
    candidates: list[list[int]] = []
    current: list[int] = []
    for start in starts:
        if not current or start - current[-1] <= config.maximum_dense_gap_units:
            current.append(start)
        else:
            if len(current) >= config.minimum_run_onsets:
                candidates.append(current)
            current = [start]
    if len(current) >= config.minimum_run_onsets:
        candidates.append(current)
    return candidates


def _interval_supported(
    left: int, right: int, intervals: tuple[tuple[int, int], ...], tolerance: int
) -> bool:
    return any(
        abs(left - interval_left) <= tolerance and abs(right - interval_right) <= tolerance
        for interval_left, interval_right in intervals
    )


def _coalesce_onsets(
    groups: list[NotationGroup], compressed_starts: set[int], maximum_chord_size: int
) -> list[NotationGroup]:
    by_timing: dict[tuple[int, int], list[NotationGroup]] = {}
    untouched = []
    for group in groups:
        if group.start_units not in compressed_starts:
            untouched.append(group)
        else:
            by_timing.setdefault((group.start_units, group.end_units), []).append(group)

    merged = []
    for (start_units, end_units), timing_groups in sorted(by_timing.items()):
        pitches = [pitch for group in timing_groups for pitch in group.pitches]
        if len(pitches) != len(set(pitches)):
            merged.extend(timing_groups)
            continue
        pitch_count = len(pitches)
        velocity = round(
            sum(group.velocity * len(group.pitches) for group in timing_groups) / pitch_count
        )
        confidence = round(
            sum(group.confidence * len(group.pitches) for group in timing_groups) / pitch_count,
            6,
        )
        ordered = sorted(pitches)
        for index in range(0, pitch_count, maximum_chord_size):
            merged.append(
                NotationGroup(
                    start_units=start_units,
                    end_units=end_units,
                    pitches=tuple(ordered[index : index + maximum_chord_size]),
                    velocity=velocity,
                    confidence=confidence,
                )
            )
    return sorted(
        [*untouched, *merged],
        key=lambda item: (item.start_units, -(item.end_units - item.start_units), item.pitches),
    )
