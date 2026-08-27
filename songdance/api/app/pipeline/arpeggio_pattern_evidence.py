from dataclasses import dataclass
from statistics import median

from app.pipeline.arpeggio_audio_evidence import (
    EvidenceTimeMap,
    matching_harmonic_observation,
)
from app.pipeline.harmonics import (
    MAXIMUM_INDEPENDENT_RELEASE_ENERGY_RATIO,
    HarmonicEvidence,
    HarmonicRemoval,
    NoteOnsetEvidence,
    supports_energy_velocity_attack,
    supports_independent_simultaneous_attack,
)
from app.pipeline.simple_arpeggio import SIMPLE_ARPEGGIO_PATTERN, _RepeatedCycleMatch
from app.pipeline.transcribe import NoteEvent

MINIMUM_RECURRENCE_CYCLES = 3
MINIMUM_INDEPENDENT_LINE_SLOTS = 3
MAXIMUM_PARTIAL_ENERGY_RATIO = 0.75
MAXIMUM_PARTIAL_VELOCITY_RATIO = 0.85
MAXIMUM_PARTIAL_DURATION_RATIO = 2.1
MAXIMUM_DECAY_SLOTS_SINCE_ATTACK = 3
MAXIMUM_DECAY_ENERGY_RATIO = 1.35
MAXIMUM_DECAY_VELOCITY_RATIO = 1.1
MAXIMUM_DECAY_DURATION_RATIO = 3.1


@dataclass(frozen=True)
class StableHarmonicEvidence:
    measurement: HarmonicRemoval
    recurrence_count: int


@dataclass(frozen=True)
class PatternDecayEvidence:
    onset: NoteOnsetEvidence
    previous: NoteEvent
    slots_since_attack: int
    energy_ratio: float
    velocity_ratio: float
    duration_ratio: float


@dataclass(frozen=True)
class PatternEvidenceIndex:
    stable_harmonics: dict[int, StableHarmonicEvidence]
    decays: dict[int, PatternDecayEvidence]
    independent_harmonics: set[int]


def build_pattern_evidence_index(
    match: _RepeatedCycleMatch,
    slot_by_group: dict[int, int],
    cycle_by_group: dict[int, int],
    selected_by_group: dict[int, NoteEvent],
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> PatternEvidenceIndex:
    harmonic_candidates: dict[int, tuple[int, NoteEvent, HarmonicRemoval]] = {}
    recurrence_cycles: dict[tuple[int, int, int, int], set[int]] = {}
    coherent_slots: dict[int, set[int]] = {}
    ordered_groups = sorted(selected_by_group)
    complete_cycle_groups = {group for cycle in match.cycles for group in cycle}

    for group_index in ordered_groups:
        selected = selected_by_group[group_index]
        slot = slot_by_group[group_index]
        for candidate in match.groups[group_index][1]:
            if candidate is selected:
                continue
            measurement = matching_harmonic_observation(candidate, selected, evidence, time_map)
            if measurement is None:
                continue
            harmonic_candidates[id(candidate)] = (group_index, candidate, measurement)
            signature = (slot, selected.pitch, candidate.pitch, measurement.harmonic_number)
            if group_index in complete_cycle_groups:
                recurrence_cycles.setdefault(signature, set()).add(cycle_by_group[group_index])
            if supports_energy_velocity_attack(measurement):
                coherent_slots.setdefault(measurement.harmonic_number, set()).add(slot)

    independent_line_slots = {
        (harmonic_number, slot)
        for harmonic_number, slots in coherent_slots.items()
        for slot in _cyclic_run_slots(
            slots,
            len(SIMPLE_ARPEGGIO_PATTERN),
            MINIMUM_INDEPENDENT_LINE_SLOTS,
        )
    }
    partial_profile = _partial_energy_profile(
        harmonic_candidates,
        recurrence_cycles,
        slot_by_group,
        selected_by_group,
    )
    independent_harmonics = {
        event_id
        for event_id, (group_index, candidate, measurement) in harmonic_candidates.items()
        if supports_energy_velocity_attack(measurement)
        and (
            (measurement.harmonic_number, slot_by_group[group_index]) in independent_line_slots
            or not _looks_like_partial(measurement, partial_profile)
        )
    }
    profile_slots = {
        slot_by_group[group_index]
        for group_index, _candidate, _measurement in harmonic_candidates.values()
    }
    stable_harmonics = {}
    for event_id, (group_index, _candidate, measurement) in harmonic_candidates.items():
        selected = selected_by_group[group_index]
        slot = slot_by_group[group_index]
        signature = (slot, selected.pitch, measurement.harmonic_pitch, measurement.harmonic_number)
        count = len(recurrence_cycles.get(signature, set()))
        if (
            len(profile_slots) >= MINIMUM_INDEPENDENT_LINE_SLOTS
            and count >= MINIMUM_RECURRENCE_CYCLES
            and (measurement.harmonic_number, slot) not in independent_line_slots
            and not measurement.independent_onset
            and not supports_independent_simultaneous_attack(measurement)
            and _looks_like_partial(measurement, partial_profile)
            and measurement.energy_ratio <= MAXIMUM_PARTIAL_ENERGY_RATIO
            and (measurement.velocity_ratio or float("inf")) <= MAXIMUM_PARTIAL_VELOCITY_RATIO
            and (measurement.duration_ratio or float("inf")) <= MAXIMUM_PARTIAL_DURATION_RATIO
        ):
            stable_harmonics[event_id] = StableHarmonicEvidence(measurement, count)

    decays = _build_decay_index(
        match,
        ordered_groups,
        selected_by_group,
        evidence,
        time_map,
        stable_harmonics,
    )
    return PatternEvidenceIndex(stable_harmonics, decays, independent_harmonics)


def _partial_energy_profile(
    candidates: dict[int, tuple[int, NoteEvent, HarmonicRemoval]],
    recurrence_cycles: dict[tuple[int, int, int, int], set[int]],
    slot_by_group: dict[int, int],
    selected_by_group: dict[int, NoteEvent],
) -> dict[int, float]:
    energies: dict[int, list[float]] = {}
    slots: dict[int, set[int]] = {}
    for group_index, _candidate, measurement in candidates.values():
        slot = slot_by_group[group_index]
        selected = selected_by_group[group_index]
        signature = (slot, selected.pitch, measurement.harmonic_pitch, measurement.harmonic_number)
        if len(
            recurrence_cycles.get(signature, set())
        ) >= MINIMUM_RECURRENCE_CYCLES and not supports_energy_velocity_attack(measurement):
            energies.setdefault(measurement.harmonic_number, []).append(measurement.energy_ratio)
            slots.setdefault(measurement.harmonic_number, set()).add(slot)
    return {
        harmonic_number: median(values)
        for harmonic_number, values in energies.items()
        if len(slots[harmonic_number]) >= MINIMUM_INDEPENDENT_LINE_SLOTS
    }


def _matches_partial_profile(
    measurement: HarmonicRemoval,
    profile: dict[int, float],
) -> bool:
    baseline = profile.get(measurement.harmonic_number)
    return baseline is not None and baseline * 0.67 <= measurement.energy_ratio <= baseline * 1.5


def _looks_like_partial(
    measurement: HarmonicRemoval,
    profile: dict[int, float],
) -> bool:
    return (
        not supports_energy_velocity_attack(measurement)
        or (
            measurement.tracking_energy_ratio is not None
            and measurement.tracking_energy_ratio >= measurement.tracking_threshold
        )
        or (
            measurement.release_energy_ratio is not None
            and measurement.release_energy_ratio > MAXIMUM_INDEPENDENT_RELEASE_ENERGY_RATIO
        )
        or _matches_partial_profile(measurement, profile)
    )


def _build_decay_index(
    match: _RepeatedCycleMatch,
    ordered_groups: list[int],
    selected_by_group: dict[int, NoteEvent],
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
    stable_harmonics: dict[int, StableHarmonicEvidence],
) -> dict[int, PatternDecayEvidence]:
    decays = {}
    for position, group_index in enumerate(ordered_groups):
        selected = selected_by_group[group_index]
        for candidate in match.groups[group_index][1]:
            if candidate is selected or id(candidate) in stable_harmonics:
                continue
            previous, distance = _previous_pattern_attack(
                candidate.pitch,
                position,
                ordered_groups,
                selected_by_group,
            )
            onset = _matching_onset(candidate, evidence, time_map)
            if previous is None or distance is None or onset is None:
                continue
            previous_duration = previous.end_sec - previous.start_sec
            candidate_duration = candidate.end_sec - candidate.start_sec
            if (
                candidate.pitch not in SIMPLE_ARPEGGIO_PATTERN
                or distance > MAXIMUM_DECAY_SLOTS_SINCE_ATTACK
                or onset.independent_onset
                or onset.pre_onset_energy is None
                or onset.onset_energy is None
                or onset.pre_onset_energy <= 0
                or previous.velocity <= 0
                or previous_duration <= 0
                or candidate_duration <= 0
            ):
                continue
            energy_ratio = onset.onset_energy / onset.pre_onset_energy
            velocity_ratio = candidate.velocity / previous.velocity
            duration_ratio = candidate_duration / previous_duration
            if (
                energy_ratio <= MAXIMUM_DECAY_ENERGY_RATIO
                and velocity_ratio <= MAXIMUM_DECAY_VELOCITY_RATIO
                and duration_ratio <= MAXIMUM_DECAY_DURATION_RATIO
            ):
                decays[id(candidate)] = PatternDecayEvidence(
                    onset,
                    previous,
                    distance,
                    energy_ratio,
                    velocity_ratio,
                    duration_ratio,
                )
    return decays


def _previous_pattern_attack(
    pitch: int,
    position: int,
    ordered_groups: list[int],
    selected_by_group: dict[int, NoteEvent],
) -> tuple[NoteEvent | None, int | None]:
    for previous_position in range(position - 1, -1, -1):
        previous = selected_by_group[ordered_groups[previous_position]]
        if previous.pitch == pitch:
            return previous, position - previous_position
    return None, None


def _matching_onset(
    candidate: NoteEvent,
    evidence: HarmonicEvidence,
    time_map: EvidenceTimeMap,
) -> NoteOnsetEvidence | None:
    matches = [
        item
        for item in evidence.onset_observations
        if item.pitch == candidate.pitch and time_map.maps(item.start_sec, candidate.start_sec)
    ]
    return (
        min(
            matches,
            key=lambda item: (
                abs((item.end_sec - item.start_sec) - (candidate.end_sec - candidate.start_sec)),
                abs(item.start_sec - candidate.start_sec),
            ),
        )
        if matches
        else None
    )


def _cyclic_run_slots(slots: set[int], cycle_length: int, minimum: int) -> set[int]:
    protected = set()
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
