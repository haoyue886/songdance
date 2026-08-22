from dataclasses import dataclass
from statistics import median

from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicRemoval,
    supports_independent_simultaneous_attack,
)
from app.pipeline.simple_arpeggio import SIMPLE_ARPEGGIO_PATTERN, _RepeatedCycleMatch
from app.pipeline.transcribe import NoteEvent

MAXIMUM_HARMONIC_VELOCITY_RATIO = 0.85
MAXIMUM_HARMONIC_DURATION_RATIO = 2.1


@dataclass(frozen=True)
class EvidenceTimeMap:
    source_origin: float
    source_step: float
    target_origin: float
    target_step: float

    def maps(self, source_time: float, target_time: float) -> bool:
        slot = round((source_time - self.source_origin) / self.source_step)
        mapped = self.target_origin + slot * self.target_step
        return abs(mapped - target_time) <= self.target_step * 0.25


def build_evidence_time_map(
    evidence: HarmonicEvidence, match: _RepeatedCycleMatch
) -> EvidenceTimeMap | None:
    starts = sorted({item.start_sec for item in evidence.onset_observations})
    if not starts:
        return None
    clusters: list[list[float]] = []
    for start in starts:
        if clusters and start - clusters[-1][-1] <= match.step_seconds * 0.25:
            clusters[-1].append(start)
        else:
            clusters.append([start])
    centers = [median(cluster) for cluster in clusters]
    deltas = [
        right - left
        for left, right in zip(centers, centers[1:], strict=False)
        if match.step_seconds * 0.6 <= right - left <= match.step_seconds * 1.4
    ]
    if len(deltas) < len(SIMPLE_ARPEGGIO_PATTERN):
        return None
    return EvidenceTimeMap(
        source_origin=centers[0],
        source_step=median(deltas),
        target_origin=match.groups[0][0],
        target_step=match.step_seconds,
    )


def has_confirmed_harmonic_pair(
    candidate: NoteEvent,
    fundamental: NoteEvent,
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> bool:
    measurement = next(
        (
            item
            for item in evidence.observations
            if _measurement_matches(item, fundamental, candidate, time_map)
        ),
        None,
    )
    if (
        measurement is not None
        and _has_independent_simultaneous_attack(measurement)
        and measurement.harmonic_number != 3
    ):
        return False
    if measurement is not None and measurement.release_probe_blocked:
        return False
    if (
        measurement is not None
        and measurement.harmonic_number == 3
        and measurement.release_energy_ratio is not None
        and measurement.release_energy_ratio <= 0.25
    ):
        return False
    if measurement is not None and measurement.release_energy_ratio is None:
        return (
            measurement.energy_ratio <= 0.22
            and measurement.velocity_ratio is not None
            and measurement.velocity_ratio <= MAXIMUM_HARMONIC_VELOCITY_RATIO
            and (measurement.duration_ratio or float("inf")) <= MAXIMUM_HARMONIC_DURATION_RATIO
        )
    return (
        measurement is not None
        and not measurement.independent_onset
        and measurement.energy_ratio <= 0.75
        and (measurement.velocity_ratio or float("inf")) <= MAXIMUM_HARMONIC_VELOCITY_RATIO
        and (measurement.duration_ratio or float("inf")) <= MAXIMUM_HARMONIC_DURATION_RATIO
    )


def has_harmonic_observation(
    candidate: NoteEvent,
    fundamental: NoteEvent,
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> bool:
    return any(
        _measurement_matches(item, fundamental, candidate, time_map)
        for item in evidence.observations
    )


def is_confirmed_same_pitch_decay(
    candidate: NoteEvent,
    group_index: int,
    selected_by_group: dict[int, NoteEvent],
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> bool:
    matching_onsets = [
        item
        for item in evidence.onset_observations
        if item.pitch == candidate.pitch and time_map.maps(item.start_sec, candidate.start_sec)
    ]
    onset = (
        min(
            matching_onsets,
            key=lambda item: (
                abs((item.end_sec - item.start_sec) - (candidate.end_sec - candidate.start_sec)),
                abs(item.start_sec - candidate.start_sec),
            ),
        )
        if matching_onsets
        else None
    )
    if onset is None or onset.independent_onset:
        return False
    return any(
        selected_by_group[index].pitch == candidate.pitch
        for index in range(group_index - 1, -1, -1)
        if index in selected_by_group
    )


def _measurement_matches(
    measurement: HarmonicRemoval,
    fundamental: NoteEvent,
    candidate: NoteEvent,
    time_map: EvidenceTimeMap,
) -> bool:
    return (
        measurement.fundamental_pitch == fundamental.pitch
        and measurement.harmonic_pitch == candidate.pitch
        and time_map.maps(measurement.harmonic_start_sec, candidate.start_sec)
        and measurement.fundamental_start_sec is not None
        and abs(
            (measurement.harmonic_start_sec - measurement.fundamental_start_sec)
            - (candidate.start_sec - fundamental.start_sec)
        )
        <= time_map.target_step * 0.25
    )


def _has_independent_simultaneous_attack(
    measurement: HarmonicRemoval,
) -> bool:
    return supports_independent_simultaneous_attack(measurement)
