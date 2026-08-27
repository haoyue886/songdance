from app.pipeline.arpeggio_audio_evidence import (
    build_evidence_time_map,
    has_confirmed_harmonic_pair,
    is_confirmed_same_pitch_decay,
)
from app.pipeline.arpeggio_audit import (
    ArpeggioFilterResult,
    ArpeggioRemovalAudit,
    audit_harmonic_removal,
    audit_pattern_decay_removal,
    audit_same_pitch_removal,
    audit_stable_harmonic_removal,
)
from app.pipeline.arpeggio_pattern_evidence import build_pattern_evidence_index
from app.pipeline.arpeggio_pedal_support import supported_cycle_indexes
from app.pipeline.harmonics import HarmonicEvidence
from app.pipeline.simple_arpeggio import (
    SIMPLE_ARPEGGIO_PATTERN,
    _has_explicit_crossing,
    _RepeatedCycleMatch,
    _stable_repeated_cycle_match,
    _trailing_pattern_slot_indexes,
)
from app.pipeline.transcribe import NoteEvent

SIMPLE_ARPEGGIO_FILTER_VERSION = "simple-arpeggio-filter-v8"
SIMPLE_ARPEGGIO_RESONANCE_FILTERED = "SIMPLE_ARPEGGIO_RESONANCE_FILTERED"
MINIMUM_PARALLEL_SLOT_RUN = 3
MINIMUM_PARALLEL_PITCH_SEPARATION = 5


def filter_simple_arpeggio_resonance(
    events: list[NoteEvent],
    *,
    pedal_intervals: tuple[tuple[float, float], ...],
    harmonic_evidence: HarmonicEvidence | None = None,
) -> ArpeggioFilterResult:
    evidence = harmonic_evidence or HarmonicEvidence.unavailable()
    if evidence.status != "available":
        return _filter_result(events)
    match = _stable_repeated_cycle_match(events)
    if match is None:
        return _filter_result(events)
    supported_cycles = supported_cycle_indexes(match, pedal_intervals)
    if not supported_cycles:
        return _filter_result(events)
    supported_ranges = tuple(match.ranges[index] for index in supported_cycles)
    if _has_explicit_crossing(events, supported_ranges):
        return _filter_result(events)

    slot_by_group = {
        group_index: slot
        for cycle_index in supported_cycles
        for slot, group_index in enumerate(match.cycles[cycle_index])
    }
    cycle_by_group = {
        group_index: cycle_index
        for cycle_index in supported_cycles
        for group_index in match.cycles[cycle_index]
    }
    if supported_cycles[-1] == len(match.cycles) - 1:
        trailing_slots = _trailing_pattern_slot_indexes(match)
        slot_by_group.update(trailing_slots)
        cycle_by_group.update({group_index: len(match.cycles) for group_index in trailing_slots})
    expected_by_group = {
        group_index: SIMPLE_ARPEGGIO_PATTERN[slot] for group_index, slot in slot_by_group.items()
    }
    time_map = build_evidence_time_map(evidence, match)
    if time_map is None:
        return _filter_result(events)
    parallel_events = _stable_parallel_event_ids(match, supported_cycles, slot_by_group)
    selected_by_group: dict[int, NoteEvent] = {}
    for group_index, (_, group) in enumerate(match.groups):
        expected_pitch = expected_by_group.get(group_index)
        if expected_pitch is None:
            continue
        candidates = [event for event in group if event.pitch == expected_pitch]
        if candidates:
            selected_by_group[group_index] = max(candidates, key=_candidate_rank)
    pattern_evidence = build_pattern_evidence_index(
        match,
        slot_by_group,
        cycle_by_group,
        selected_by_group,
        evidence,
        time_map,
    )

    removed_ids: set[int] = set()
    removals: list[ArpeggioRemovalAudit] = []
    previous_by_pitch: dict[int, NoteEvent] = {}
    for group_index, (_, group) in enumerate(match.groups):
        selected = selected_by_group.get(group_index)
        if selected is None:
            previous_by_pitch.update({event.pitch: event for event in group})
            continue
        for event in group:
            if event is selected:
                continue
            harmonic_measurement = has_confirmed_harmonic_pair(event, selected, evidence, time_map)
            same_pitch_evidence = is_confirmed_same_pitch_decay(
                event,
                previous_by_pitch,
                evidence,
                time_map,
            )
            stable_harmonic = pattern_evidence.stable_harmonics.get(id(event))
            pattern_decay = pattern_evidence.decays.get(id(event))
            if (
                id(event) in parallel_events
                or id(event) in pattern_evidence.independent_harmonics
                or _is_independent_pattern_voice(event, expected_by_group, match.groups)
            ):
                continue
            if harmonic_measurement is not None:
                removed_ids.add(id(event))
                removals.append(
                    audit_harmonic_removal(
                        event,
                        selected,
                        group_index,
                        cycle_by_group[group_index],
                        slot_by_group[group_index],
                        harmonic_measurement,
                    )
                )
            elif stable_harmonic is not None:
                removed_ids.add(id(event))
                removals.append(
                    audit_stable_harmonic_removal(
                        event,
                        selected,
                        group_index,
                        cycle_by_group[group_index],
                        slot_by_group[group_index],
                        stable_harmonic,
                    )
                )
            elif same_pitch_evidence is not None:
                removed_ids.add(id(event))
                removals.append(
                    audit_same_pitch_removal(
                        event,
                        same_pitch_evidence.previous,
                        group_index,
                        cycle_by_group[group_index],
                        slot_by_group[group_index],
                        same_pitch_evidence,
                    )
                )
            elif pattern_decay is not None:
                removed_ids.add(id(event))
                removals.append(
                    audit_pattern_decay_removal(
                        event,
                        group_index,
                        cycle_by_group[group_index],
                        slot_by_group[group_index],
                        pattern_decay,
                    )
                )
        previous_by_pitch.update({event.pitch: event for event in group})
    return _filter_result(
        [event for event in events if id(event) not in removed_ids],
        removals=tuple(removals),
        stable_cycle_count=len(supported_cycles),
        matched_slot_count=len(expected_by_group),
    )


def _candidate_rank(event: NoteEvent) -> tuple[float, int, float]:
    return event.confidence, event.velocity, event.end_sec - event.start_sec


def _stable_parallel_event_ids(
    match: _RepeatedCycleMatch,
    supported_cycles: tuple[int, ...],
    slot_by_group: dict[int, int],
) -> set[int]:
    parallel_by_slot: dict[int, set[int]] = {}
    sustained_slots: set[int] = set()
    for slot, expected_pitch in enumerate(SIMPLE_ARPEGGIO_PATTERN):
        pitch_sets = []
        for cycle_index in supported_cycles:
            group_index = match.cycles[cycle_index][slot]
            pitch_sets.append(
                {
                    event.pitch
                    for event in match.groups[group_index][1]
                    if event.pitch != expected_pitch
                    and abs(event.pitch - expected_pitch) >= MINIMUM_PARALLEL_PITCH_SEPARATION
                }
            )
        common = set.intersection(*pitch_sets) if pitch_sets else set()
        if common:
            parallel_by_slot[slot] = common
        if any(
            all(
                any(
                    event.pitch == pitch
                    and event.end_sec >= match.groups[group_index][0] + match.step_seconds * 0.8
                    for event in match.groups[group_index][1]
                )
                for cycle_index in supported_cycles
                for group_index in (match.cycles[cycle_index][slot],)
            )
            for pitch in common
        ):
            sustained_slots.add(slot)

    if len(parallel_by_slot) == len(SIMPLE_ARPEGGIO_PATTERN):
        protected_slots = set(parallel_by_slot)
    else:
        protected_slots = _cyclic_run_slots(
            sustained_slots,
            len(SIMPLE_ARPEGGIO_PATTERN),
            MINIMUM_PARALLEL_SLOT_RUN,
        )
    return {
        id(event)
        for group_index, slot in slot_by_group.items()
        for event in match.groups[group_index][1]
        if slot in protected_slots and event.pitch in parallel_by_slot[slot]
    }


def _cyclic_run_slots(slots: set[int], cycle_length: int, minimum: int) -> set[int]:
    protected: set[int] = set()
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


def _is_independent_pattern_voice(
    event: NoteEvent,
    expected_by_group: dict[int, int],
    groups: tuple[tuple[float, tuple[NoteEvent, ...]], ...],
) -> bool:
    separated_slots = sum(
        event.start_sec < groups[index][0] < event.end_sec
        and abs(event.pitch - expected_pitch) >= 5
        for index, expected_pitch in expected_by_group.items()
    )
    return separated_slots >= 3


def _filter_result(
    events: list[NoteEvent],
    *,
    removals: tuple[ArpeggioRemovalAudit, ...] = (),
    stable_cycle_count: int = 0,
    matched_slot_count: int = 0,
) -> ArpeggioFilterResult:
    return ArpeggioFilterResult(
        events=events,
        version=SIMPLE_ARPEGGIO_FILTER_VERSION,
        applied=bool(removals),
        removed_event_count=len(removals),
        stable_cycle_count=stable_cycle_count,
        matched_slot_count=matched_slot_count,
        reason_codes=(SIMPLE_ARPEGGIO_RESONANCE_FILTERED,) if removals else (),
        removals=removals,
    )
