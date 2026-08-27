from dataclasses import asdict, dataclass

from app.pipeline.arpeggio_audio_evidence import SamePitchDecayEvidence
from app.pipeline.arpeggio_pattern_evidence import (
    PatternDecayEvidence,
    StableHarmonicEvidence,
)
from app.pipeline.harmonics import HarmonicRemoval
from app.pipeline.transcribe import NoteEvent


@dataclass(frozen=True)
class ArpeggioRemovalAudit:
    candidate_pitch: int
    candidate_start_sec: float
    candidate_end_sec: float
    group_index: int
    cycle_index: int
    slot_index: int
    selected_pitch: int
    selected_start_sec: float
    selected_end_sec: float
    evidence_type: str
    harmonic_order: int | None
    energy_ratio: float | None
    independent_onset: bool
    onset_growth: float | None
    onset_delta_seconds: float | None
    velocity_ratio: float | None
    duration_ratio: float | None
    release_energy_ratio: float | None
    tracking_energy_ratio: float | None
    tracking_threshold: float | None
    release_probe_blocked: bool
    pre_onset_energy: float | None
    onset_energy: float | None
    overlap_seconds: float | None
    recurrence_count: int | None
    slots_since_attack: int | None
    decision_reason: str

    def summary(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ArpeggioFilterResult:
    events: list[NoteEvent]
    version: str
    applied: bool
    removed_event_count: int
    stable_cycle_count: int
    matched_slot_count: int
    reason_codes: tuple[str, ...]
    removals: tuple[ArpeggioRemovalAudit, ...]

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "applied": self.applied,
            "removed_event_count": self.removed_event_count,
            "stable_cycle_count": self.stable_cycle_count,
            "matched_slot_count": self.matched_slot_count,
            "reason_codes": self.reason_codes,
            "removals": [item.summary() for item in self.removals],
        }


def audit_harmonic_removal(
    candidate: NoteEvent,
    selected: NoteEvent,
    group_index: int,
    cycle_index: int,
    slot_index: int,
    measurement: HarmonicRemoval,
) -> ArpeggioRemovalAudit:
    return ArpeggioRemovalAudit(
        candidate.pitch,
        candidate.start_sec,
        candidate.end_sec,
        group_index,
        cycle_index,
        slot_index,
        selected.pitch,
        selected.start_sec,
        selected.end_sec,
        "harmonic_pair",
        measurement.harmonic_number,
        measurement.energy_ratio,
        measurement.independent_onset,
        measurement.onset_growth,
        measurement.onset_delta_seconds,
        measurement.velocity_ratio,
        measurement.duration_ratio,
        measurement.release_energy_ratio,
        measurement.tracking_energy_ratio,
        measurement.tracking_threshold,
        measurement.release_probe_blocked,
        None,
        None,
        None,
        None,
        None,
        "CONFIRMED_HARMONIC_PAIR",
    )


def audit_same_pitch_removal(
    candidate: NoteEvent,
    previous: NoteEvent,
    group_index: int,
    cycle_index: int,
    slot_index: int,
    evidence: SamePitchDecayEvidence,
) -> ArpeggioRemovalAudit:
    return ArpeggioRemovalAudit(
        candidate.pitch,
        candidate.start_sec,
        candidate.end_sec,
        group_index,
        cycle_index,
        slot_index,
        previous.pitch,
        previous.start_sec,
        previous.end_sec,
        "same_pitch_decay",
        None,
        evidence.energy_ratio,
        evidence.onset.independent_onset,
        evidence.onset.onset_growth,
        candidate.start_sec - previous.start_sec,
        evidence.velocity_ratio,
        evidence.duration_ratio,
        None,
        None,
        None,
        False,
        evidence.onset.pre_onset_energy,
        evidence.onset.onset_energy,
        evidence.overlap_seconds,
        None,
        None,
        "CONFIRMED_SAME_PITCH_DECAY",
    )


def audit_stable_harmonic_removal(
    candidate: NoteEvent,
    selected: NoteEvent,
    group_index: int,
    cycle_index: int,
    slot_index: int,
    evidence: StableHarmonicEvidence,
) -> ArpeggioRemovalAudit:
    measurement = evidence.measurement
    return ArpeggioRemovalAudit(
        candidate.pitch,
        candidate.start_sec,
        candidate.end_sec,
        group_index,
        cycle_index,
        slot_index,
        selected.pitch,
        selected.start_sec,
        selected.end_sec,
        "stable_harmonic_partial",
        measurement.harmonic_number,
        measurement.energy_ratio,
        measurement.independent_onset,
        measurement.onset_growth,
        measurement.onset_delta_seconds,
        measurement.velocity_ratio,
        measurement.duration_ratio,
        measurement.release_energy_ratio,
        measurement.tracking_energy_ratio,
        measurement.tracking_threshold,
        measurement.release_probe_blocked,
        None,
        None,
        None,
        evidence.recurrence_count,
        None,
        "STABLE_HARMONIC_PARTIAL",
    )


def audit_pattern_decay_removal(
    candidate: NoteEvent,
    group_index: int,
    cycle_index: int,
    slot_index: int,
    evidence: PatternDecayEvidence,
) -> ArpeggioRemovalAudit:
    previous = evidence.previous
    return ArpeggioRemovalAudit(
        candidate.pitch,
        candidate.start_sec,
        candidate.end_sec,
        group_index,
        cycle_index,
        slot_index,
        previous.pitch,
        previous.start_sec,
        previous.end_sec,
        "pattern_decay",
        None,
        evidence.energy_ratio,
        evidence.onset.independent_onset,
        evidence.onset.onset_growth,
        candidate.start_sec - previous.start_sec,
        evidence.velocity_ratio,
        evidence.duration_ratio,
        None,
        None,
        None,
        False,
        evidence.onset.pre_onset_energy,
        evidence.onset.onset_energy,
        None,
        None,
        evidence.slots_since_attack,
        "CONFIRMED_PATTERN_DECAY",
    )
