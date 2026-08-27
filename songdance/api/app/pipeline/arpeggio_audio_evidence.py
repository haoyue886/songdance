from dataclasses import dataclass
from statistics import median

from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicRemoval,
    NoteOnsetEvidence,
    supports_independent_simultaneous_attack,
)
from app.pipeline.simple_arpeggio import SIMPLE_ARPEGGIO_PATTERN, _RepeatedCycleMatch
from app.pipeline.transcribe import NoteEvent

MAXIMUM_HARMONIC_VELOCITY_RATIO = 0.85
MAXIMUM_HARMONIC_DURATION_RATIO = 2.1
MAXIMUM_SAME_PITCH_ENERGY_RATIO = 1.25
MAXIMUM_SAME_PITCH_VELOCITY_RATIO = 0.85
MAXIMUM_SAME_PITCH_DURATION_RATIO = 2.1


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


@dataclass(frozen=True)
class SamePitchDecayEvidence:
    onset: NoteOnsetEvidence
    previous: NoteEvent
    overlap_seconds: float
    energy_ratio: float
    velocity_ratio: float
    duration_ratio: float


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
) -> HarmonicRemoval | None:
    measurement = next(
        (
            item
            for item in evidence.observations
            if _measurement_matches(item, fundamental, candidate, time_map)
        ),
        None,
    )
    if measurement is not None and _has_independent_simultaneous_attack(measurement):
        return None
    if measurement is not None and measurement.release_energy_ratio is None:
        return None
    confirmed = (
        measurement is not None
        and not measurement.independent_onset
        and measurement.energy_ratio <= 0.75
        and (measurement.velocity_ratio or float("inf")) <= MAXIMUM_HARMONIC_VELOCITY_RATIO
        and (measurement.duration_ratio or float("inf")) <= MAXIMUM_HARMONIC_DURATION_RATIO
    )
    return measurement if confirmed else None


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


def matching_harmonic_observation(
    candidate: NoteEvent,
    fundamental: NoteEvent,
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> HarmonicRemoval | None:
    return next(
        (
            item
            for item in evidence.observations
            if _measurement_matches(item, fundamental, candidate, time_map)
        ),
        None,
    )


def is_confirmed_same_pitch_decay(
    candidate: NoteEvent,
    previous_by_pitch: dict[int, NoteEvent],
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> SamePitchDecayEvidence | None:
    previous = previous_by_pitch.get(candidate.pitch)
    if previous is None:
        return None
    overlap_seconds = previous.end_sec - candidate.start_sec
    if overlap_seconds <= 0:
        return None
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
    if (
        onset is None
        or onset.independent_onset
        or onset.pre_onset_energy is None
        or onset.onset_energy is None
        or onset.pre_onset_energy <= 0
    ):
        return None
    previous_duration = previous.end_sec - previous.start_sec
    candidate_duration = candidate.end_sec - candidate.start_sec
    if previous.velocity <= 0 or previous_duration <= 0 or candidate_duration <= 0:
        return None
    energy_ratio = onset.onset_energy / onset.pre_onset_energy
    velocity_ratio = candidate.velocity / previous.velocity
    duration_ratio = candidate_duration / previous_duration
    if (
        energy_ratio > MAXIMUM_SAME_PITCH_ENERGY_RATIO
        or velocity_ratio > MAXIMUM_SAME_PITCH_VELOCITY_RATIO
        or duration_ratio > MAXIMUM_SAME_PITCH_DURATION_RATIO
    ):
        return None
    return SamePitchDecayEvidence(
        onset=onset,
        previous=previous,
        overlap_seconds=overlap_seconds,
        energy_ratio=energy_ratio,
        velocity_ratio=velocity_ratio,
        duration_ratio=duration_ratio,
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
