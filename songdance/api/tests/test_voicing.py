from dataclasses import replace

from app.pipeline.arpeggio_resonance import (
    SIMPLE_ARPEGGIO_RESONANCE_FILTERED,
    filter_simple_arpeggio_resonance,
)
from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicEvidenceConfig,
    HarmonicRemoval,
    NoteOnsetEvidence,
)
from app.pipeline.harmony import HarmonyConfig, NotationGroup, group_harmony
from app.pipeline.score import build_score
from app.pipeline.simple_arpeggio import (
    SIMPLE_ARPEGGIO_APPLIED,
    SIMPLE_ARPEGGIO_CLEAR_ZONE,
    SIMPLE_ARPEGGIO_REJECTED_CROSSING,
    SIMPLE_ARPEGGIO_STABLE_TIMING,
)
from app.pipeline.staff_distribution import (
    STAFF_DISTRIBUTION_SUSPECT,
    staff_distribution_summary,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voicing import (
    VoicingConfig,
    _has_dense_two_hand_texture,
    assign_hands,
    assign_voices,
)


def _audio_evidence(
    *,
    harmonic_pairs: tuple[tuple[NoteEvent, NoteEvent], ...] = (),
    independent_harmonic_pairs: bool = False,
    decays: tuple[NoteEvent, ...] = (),
    independent: tuple[NoteEvent, ...] = (),
    decay_growth: float = 1.0,
) -> HarmonicEvidence:
    return HarmonicEvidence(
        version=HarmonicEvidenceConfig().version,
        status="available",
        source="AUDIO_STFT",
        removals=(),
        observations=tuple(
            HarmonicRemoval(
                fundamental_pitch=fundamental.pitch,
                harmonic_pitch=harmonic.pitch,
                harmonic_start_sec=harmonic.start_sec,
                harmonic_end_sec=harmonic.end_sec,
                harmonic_number=2,
                tuning_error_cents=0.0,
                energy_ratio=0.1,
                independent_onset=independent_harmonic_pairs,
                fundamental_start_sec=fundamental.start_sec,
                fundamental_end_sec=fundamental.end_sec,
                fundamental_velocity=fundamental.velocity,
                harmonic_velocity=harmonic.velocity,
                onset_delta_seconds=harmonic.start_sec - fundamental.start_sec,
                velocity_ratio=harmonic.velocity / fundamental.velocity,
                duration_ratio=(harmonic.end_sec - harmonic.start_sec)
                / (fundamental.end_sec - fundamental.start_sec),
                release_energy_ratio=0.5,
            )
            for fundamental, harmonic in harmonic_pairs
        ),
        onset_observations=tuple(
            NoteOnsetEvidence(
                pitch=event.pitch,
                start_sec=event.start_sec,
                end_sec=event.end_sec,
                onset_growth=(decay_growth if any(event is decay for decay in decays) else 3.0),
                independent_onset=(
                    not any(event is decay for decay in decays)
                    and any(event is item for item in independent)
                ),
                pre_onset_energy=1.0,
                onset_energy=(decay_growth if any(event is decay for decay in decays) else 3.0),
            )
            for event in (*decays, *independent)
        ),
    )


def test_harmony_groups_only_matching_onsets_and_near_equal_durations() -> None:
    events = [
        NoteEvent(0.0, 0.50, 60, 80, 0.8),
        NoteEvent(0.0, 0.62, 64, 90, 0.9),
        NoteEvent(0.0, 1.00, 67, 95, 0.95),
        NoteEvent(0.25, 0.75, 72, 88, 0.88),
    ]

    groups = group_harmony(events, 0.5, 0, HarmonyConfig())

    assert sorted(group.pitches for group in groups) == [(60, 64), (67,), (72,)]


def test_harmony_caps_chords_at_four_notes() -> None:
    events = [NoteEvent(0, 1, pitch, 90, 0.9) for pitch in (48, 55, 60, 64, 67)]

    groups = group_harmony(events, 0.5, 0)

    assert [len(group.pitches) for group in groups] == [4, 1]


def test_voicing_tracks_crossing_lines_and_marks_ambiguous_center_unknown() -> None:
    events = []
    for index, (left_pitch, right_pitch) in enumerate(
        ((48, 72), (51, 69), (54, 66), (57, 63), (60, 60), (63, 57))
    ):
        events.extend(
            (
                NoteEvent(float(index), index + 0.8, left_pitch, 80, 0.9),
                NoteEvent(float(index), index + 0.7, right_pitch, 90, 0.9),
            )
        )

    result = assign_hands(events)
    at_center = [event for event in result.events if event.start_sec == 4]
    after_crossing = [event for event in result.events if event.start_sec == 5]

    assert all(event.hand is None for event in at_center)
    assert {(event.pitch, event.hand) for event in after_crossing} == {
        (63, "left"),
        (57, "right"),
    }
    assert all(event.hand_confidence is not None for event in result.events)


def test_voicing_allows_an_ambiguous_middle_note_to_remain_unknown() -> None:
    result = assign_hands([NoteEvent(0, 1, 60, 90, 0.9)])

    assert result.unknown_count == 1
    assert result.events[0].hand is None
    assert result.events[0].hand_confidence is not None


def test_k545_like_texture_keeps_both_staffs_populated_without_history_starvation() -> None:
    events = [
        NoteEvent(index * 0.125, index * 0.125 + 0.1, pitch, 84, 0.9)
        for index in range(40)
        for pitch in (48 + index % 8, 64 + index % 5, 72 + index % 4)
    ]

    result = assign_hands(events)
    distribution = staff_distribution_summary(result.events)

    assert result.unknown_count == 0
    assert result.left_count == 40
    assert result.right_count == 80
    assert distribution["status"] == "passed"
    assert distribution["known_ratio"] >= 0.9


def test_staff_distribution_gate_rejects_wide_texture_with_an_empty_hand() -> None:
    events = [
        NoteEvent(
            onset * 0.25,
            onset * 0.25 + 0.2,
            pitch,
            84,
            0.9,
            hand="right",
            hand_confidence=1.0,
        )
        for onset in range(20)
        for pitch in (48, 76)
    ]

    distribution = staff_distribution_summary(events)

    assert distribution["status"] == "suspect"
    assert distribution["reason_code"] == STAFF_DISTRIBUTION_SUSPECT


def test_staff_distribution_gate_rejects_equal_but_swapped_staffs() -> None:
    events = [
        NoteEvent(
            onset * 0.25,
            onset * 0.25 + 0.2,
            pitch,
            84,
            0.9,
            hand=hand,
            hand_confidence=1.0,
        )
        for onset in range(20)
        for pitch, hand in ((48, "right"), (76, "left"))
    ]

    distribution = staff_distribution_summary(events)

    assert distribution["minority_ratio"] == 0.5
    assert distribution["bass_assignment_ratio"] == 0.0
    assert distribution["treble_assignment_ratio"] == 0.0
    assert distribution["status"] == "suspect"


def test_staff_distribution_gate_checks_each_bass_measure() -> None:
    events = [
        NoteEvent(
            measure * 2 + onset * 0.25,
            measure * 2 + onset * 0.25 + 0.2,
            pitch,
            84,
            0.9,
            hand=hand,
            hand_confidence=1.0,
        )
        for measure in range(4)
        for onset in range(4)
        for pitch, hand in (
            (48, "left" if measure < 2 else "right"),
            (76, "right"),
        )
    ]

    distribution = staff_distribution_summary(events)

    assert distribution["bass_measure_coverage_ratio"] == 0.5
    assert distribution["suspect_measure_count"] == 2
    assert distribution["status"] == "suspect"


def test_dense_texture_activation_boundaries_are_explicit() -> None:
    def texture(event_count: int, wide_onsets: int) -> list[NoteEvent]:
        events = [NoteEvent(index, index + 0.2, 60, 80, 0.9) for index in range(event_count)]
        for index in range(min(wide_onsets, event_count)):
            pitch = 48 if index % 2 == 0 else 76
            events[index] = NoteEvent(index // 2, index // 2 + 0.2, pitch, 80, 0.9)
        return events

    assert _has_dense_two_hand_texture(texture(31, 8)) is False
    assert _has_dense_two_hand_texture(texture(32, 6)) is False
    assert _has_dense_two_hand_texture(texture(32, 8)) is True


def test_simple_arpeggio_uses_stable_zones_for_ac072_sequence() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.5, index * 0.5 + 0.4, pitch, 90, 0.9)
        for index, pitch in enumerate(pitches)
    ]

    result = assign_hands(events)

    assert [event.hand for event in result.events] == [
        "left",
        "left",
        "right",
        "right",
        "right",
        "right",
        "right",
        "right",
    ]
    assert result.strategy == "simple_arpeggio_stable_zone"
    assert result.reason_codes == (
        SIMPLE_ARPEGGIO_APPLIED,
        SIMPLE_ARPEGGIO_STABLE_TIMING,
        SIMPLE_ARPEGGIO_CLEAR_ZONE,
    )
    assert all((event.hand_confidence or 0.0) >= 0.92 for event in result.events)


def test_simple_arpeggio_does_not_override_explicit_crossing_hands() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(
            index * 0.5,
            index * 0.5 + 0.4,
            pitch,
            90,
            0.9,
            hand="right" if index == 0 else None,
        )
        for index, pitch in enumerate(pitches)
    ]

    result = assign_hands(events)

    assert result.events[0].hand == "right"
    assert result.strategy == "continuity"
    assert result.reason_codes == (SIMPLE_ARPEGGIO_REJECTED_CROSSING,)


def test_score_pipeline_preserves_explicit_crossing_hands() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(
            index * 0.5,
            index * 0.5 + 0.4,
            pitch,
            90,
            0.9,
            hand="right" if index == 0 else None,
        )
        for index, pitch in enumerate(pitches)
    ]

    scored = build_score(events)

    assert scored.notes[0].hand == "right"
    assert scored.reconstruction["voicing"]["strategy"] == "continuity"
    assert scored.reconstruction["voicing"]["reason_codes"] == (SIMPLE_ARPEGGIO_REJECTED_CROSSING,)


def test_simple_arpeggio_rejects_unstable_onset_period() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    starts = (0.0, 0.1, 1.7, 2.0, 4.3, 4.4, 10.0, 10.1)
    events = [
        NoteEvent(start, start + 0.04, pitch, 90, 0.9)
        for start, pitch in zip(starts, pitches, strict=True)
    ]

    result = assign_hands(events)

    assert result.strategy == "continuity"
    assert result.reason_codes == ()
    assert all(event.hand != "left" or event.pitch <= 60 for event in result.events)


def test_simple_arpeggio_rejects_out_of_zone_transposition() -> None:
    pitches = (72, 79, 84, 88, 91, 96, 91, 88)
    events = [
        NoteEvent(index * 0.5, index * 0.5 + 0.4, pitch, 90, 0.9)
        for index, pitch in enumerate(pitches)
    ]

    result = assign_hands(events)

    assert result.strategy == "continuity"
    assert result.reason_codes == ()
    assert all(event.hand == "right" for event in result.events)
    assert all(event.hand_confidence is not None for event in result.events)


def test_repeated_arpeggio_ignores_resonant_candidates_before_stabilizing() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events: list[NoteEvent] = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
        if index:
            previous_pitch = (pattern * 3)[index - 1]
            events.append(NoteEvent(start, start + 0.2, previous_pitch, 55, 0.4))
        events.append(NoteEvent(start, start + 0.1, pitch + 12, 45, 0.35))

    result = assign_hands(events)

    assert result.strategy == "simple_arpeggio_stable_zone"
    assert result.reason_codes[0] == SIMPLE_ARPEGGIO_APPLIED
    assert all(
        event.hand == "left" if event.pitch < 60 else event.hand == "right"
        for event in result.events
    )


def test_pedal_supported_arpeggio_filters_wrong_slot_resonance_candidates() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [NoteEvent(0.0, 6.0, 36, 90, 0.9)]
    resonances = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
        if index:
            previous_pitch = (pattern * 3)[index - 1]
            resonance = NoteEvent(start, start + 0.2, previous_pitch, 55, 0.4)
            events.append(resonance)
            resonances.append(resonance)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(decays=tuple(resonances), independent=tuple(events)),
    )
    filtered_pattern = [event.pitch for event in result.events if event.pitch != 36]

    assert filtered_pattern == list(pattern * 3)
    assert any(event.pitch == 36 and event.end_sec == 6.0 for event in result.events)
    assert result.applied is True
    assert result.removed_event_count == 23
    assert len(result.removals) == result.removed_event_count
    assert result.stable_cycle_count == 3
    assert result.matched_slot_count == 24
    assert result.reason_codes == (SIMPLE_ARPEGGIO_RESONANCE_FILTERED,)
    assert all(item.energy_ratio == 1.0 for item in result.removals)
    assert all(item.velocity_ratio == 55 / 90 for item in result.removals)
    assert all(abs((item.duration_ratio or 0.0) - 0.5) < 1e-9 for item in result.removals)
    assert all(item.evidence_type == "same_pitch_decay" for item in result.removals)
    assert all((item.overlap_seconds or 0) > 0 for item in result.removals)
    assert all(item.pre_onset_energy == 1.0 for item in result.removals)
    assert all(item.onset_energy == 1.0 for item in result.removals)


def test_arpeggio_filter_uses_pattern_decay_after_previous_note_ended() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events: list[NoteEvent] = []
    candidates = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.2, pitch, 90, 0.9))
        if index:
            candidate = NoteEvent(start, start + 0.15, (pattern * 3)[index - 1], 55, 0.4)
            events.append(candidate)
            candidates.append(candidate)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(decays=tuple(candidates), independent=tuple(events)),
    )

    assert all(candidate not in result.events for candidate in candidates)
    assert result.removed_event_count == len(candidates)
    assert {item.evidence_type for item in result.removals} == {"pattern_decay"}
    assert all(item.overlap_seconds is None for item in result.removals)
    assert all((item.slots_since_attack or 0) <= 3 for item in result.removals)


def test_arpeggio_filter_keeps_overlapping_same_pitch_with_energy_growth() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events: list[NoteEvent] = []
    candidates = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
        if index:
            candidate = NoteEvent(start, start + 0.2, (pattern * 3)[index - 1], 55, 0.4)
            events.append(candidate)
            candidates.append(candidate)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(
            decays=tuple(candidates),
            independent=tuple(events),
            decay_growth=1.5,
        ),
    )

    assert all(candidate in result.events for candidate in candidates)
    assert result.removed_event_count == 0


def test_pedal_supported_arpeggio_filters_weak_slot_harmonics() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    harmonics = []
    pairs = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        fundamental = NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        events.append(fundamental)
        if pitch == 60:
            harmonic = NoteEvent(start, start + 0.2, 79, 55, 0.45)
            events.append(harmonic)
            harmonics.append(harmonic)
            pairs.append((fundamental, harmonic))

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(
            harmonic_pairs=tuple(pairs),
            decays=tuple(harmonics),
            independent=tuple(event for event in events if event not in harmonics),
        ),
    )

    assert all(harmonic not in result.events for harmonic in harmonics)
    assert [event.pitch for event in result.events] == list(pattern * 3)
    assert result.removed_event_count == 3
    assert len(result.removals) == result.removed_event_count
    assert {item.evidence_type for item in result.removals} == {"harmonic_pair"}
    assert all(item.harmonic_order == 2 for item in result.removals)
    assert all(item.release_energy_ratio == 0.5 for item in result.removals)


def test_arpeggio_filter_keeps_three_slot_coherent_octave_line() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    octaves = []
    pairs = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        fundamental = NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        events.append(fundamental)
        if 3 <= index % len(pattern) < 6:
            octave = NoteEvent(start, start + 0.15, pitch + 12, 45, 0.8)
            events.append(octave)
            octaves.append(octave)
            pairs.append((fundamental, octave))

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(
            harmonic_pairs=tuple(pairs),
            independent=tuple(events),
        ),
    )

    assert all(octave in result.events for octave in octaves)
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_single_slot_octave_above_partial_profile() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    true_octaves = []
    pairs = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        fundamental = NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        events.append(fundamental)
        slot = index % len(pattern)
        if slot == 2:
            candidate = NoteEvent(start, start + 0.4, pitch + 12, 45, 0.8)
            true_octaves.append(candidate)
        elif slot in {3, 4}:
            candidate = NoteEvent(start, start + 0.1, pitch + 12, 45, 0.8)
        else:
            continue
        events.append(candidate)
        pairs.append((fundamental, candidate))
    base_evidence = _audio_evidence(
        harmonic_pairs=tuple(pairs),
        independent=tuple(events),
    )
    evidence = replace(
        base_evidence,
        observations=tuple(
            replace(
                item,
                energy_ratio=0.25 if item.fundamental_pitch == 60 else 0.1,
                duration_ratio=1.0 if item.fundamental_pitch == 60 else 0.25,
                release_energy_ratio=None,
            )
            for item in base_evidence.observations
        ),
    )

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    assert all(octave in result.events for octave in true_octaves)


def test_arpeggio_filter_keeps_stable_out_of_pattern_parallel_voice() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    parallel = (79, 81, 84, 83, 86, 84, 86, 83)
    events = []
    for index, (primary, secondary) in enumerate(zip(pattern * 3, parallel * 3, strict=True)):
        start = index * 0.25
        events.extend(
            (
                NoteEvent(start, start + 0.2, primary, 90, 0.9),
                NoteEvent(start, start + 0.2, secondary, 55, 0.45),
            )
        )

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 6.0),))

    assert len(result.events) == 48
    assert sum(event.velocity == 55 for event in result.events) == 24
    assert result.removed_event_count == 0


def test_arpeggio_resonance_filter_requires_pedal_evidence() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.4, pitch, 90, 0.9)
        for index, pitch in enumerate(pattern * 3)
    ]
    events.append(NoteEvent(0.25, 0.5, 48, 55, 0.4))

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=(),
        harmonic_evidence=_audio_evidence(decays=(events[-1],)),
    )

    assert result.events is events
    assert result.applied is False
    assert result.removed_event_count == 0
    assert result.stable_cycle_count == 0
    assert result.matched_slot_count == 0


def test_arpeggio_resonance_filter_requires_three_stable_cycles() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.4, pitch, 90, 0.9)
        for index, pitch in enumerate(pattern * 2)
    ]
    events.append(NoteEvent(0.25, 0.5, 48, 55, 0.4))

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 4.0),),
        harmonic_evidence=_audio_evidence(decays=(events[-1],)),
    )

    assert result.events is events
    assert result.applied is False
    assert result.stable_cycle_count == 0


def test_arpeggio_resonance_filter_rejects_unstable_cycle_timing() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    for cycle_start in (0.0, 2.0, 6.0):
        for index, pitch in enumerate(pattern):
            start = cycle_start + index * 0.25
            events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
    resonance = NoteEvent(2.25, 2.5, 48, 55, 0.4)
    events.append(resonance)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 8.0),),
        harmonic_evidence=_audio_evidence(decays=(resonance,), independent=tuple(events)),
    )

    assert result.events is events
    assert resonance in result.events
    assert result.applied is False


def test_arpeggio_resonance_filter_preserves_explicit_crossing_hands() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(
            index * 0.25,
            index * 0.25 + 0.4,
            pitch,
            90,
            0.9,
            hand="right" if index == 0 else None,
        )
        for index, pitch in enumerate(pattern * 3)
    ]
    resonance = NoteEvent(0.25, 0.5, 48, 55, 0.4)
    events.append(resonance)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 8.0),),
        harmonic_evidence=_audio_evidence(decays=(resonance,), independent=tuple(events)),
    )

    assert result.events is events
    assert resonance in result.events
    assert result.applied is False


def test_arpeggio_filter_ignores_low_confidence_inferred_crossing() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(
            index * 0.25,
            index * 0.25 + 0.4,
            pitch,
            90,
            0.9,
            hand="left" if index == 23 else None,
            hand_confidence=0.7 if index == 23 else None,
        )
        for index, pitch in enumerate(pattern * 3)
    ]
    resonance = NoteEvent(0.25, 0.5, 48, 55, 0.4)
    events.append(resonance)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 8.0),),
        harmonic_evidence=_audio_evidence(decays=(resonance,), independent=tuple(events)),
    )

    assert resonance not in result.events
    assert result.applied is True


def test_arpeggio_filter_keeps_independent_pattern_pitch_voice() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.2, pitch, 90, 0.9)
        for index, pitch in enumerate(pattern * 3)
    ]
    sustained = NoteEvent(0.25, 2.0, 48, 88, 0.85)
    events.append(sustained)

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 6.0),))

    assert sustained in result.events
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_strong_repeated_octave_chords() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    octaves = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        fundamental = NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        events.append(fundamental)
        if pitch == 60:
            octave = NoteEvent(start, start + 0.4, 72, 100, 0.95)
            events.append(octave)
            octaves.append(octave)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(independent=tuple(events)),
    )

    assert all(octave in result.events for octave in octaves)
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_weak_independent_cross_hand_notes() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    cross_hand = []
    pairs = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        fundamental = NoteEvent(start, start + 0.4, pitch, 90, 0.9)
        events.append(fundamental)
        if pitch == 60:
            note = NoteEvent(start, start + 0.2, 79, 40, 0.5, hand="right")
            events.append(note)
            cross_hand.append(note)
            pairs.append((fundamental, note))

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(
            harmonic_pairs=tuple(pairs),
            independent_harmonic_pairs=True,
            independent=tuple(events),
        ),
    )

    assert all(note in result.events for note in cross_hand)
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_single_slot_chord_without_audio_pair() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = []
    chord_notes = []
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
        if pitch == 60:
            note = NoteEvent(start, start + 0.3, 76, 45, 0.6)
            events.append(note)
            chord_notes.append(note)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=_audio_evidence(),
    )

    assert all(note in result.events for note in chord_notes)
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_a_stable_parallel_pattern_voice() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    parallel = (55, 60, 48, 72, 55, 64, 55, 72)
    events = []
    for index, (primary, secondary) in enumerate(zip(pattern * 3, parallel * 3, strict=True)):
        start = index * 0.25
        events.extend(
            (
                NoteEvent(start, start + 0.2, primary, 90, 0.9),
                NoteEvent(start, start + 0.2, secondary, 88, 0.88),
            )
        )

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 6.0),))

    assert len(result.events) == 48
    assert sum(event.velocity == 88 for event in result.events) == 24
    assert result.removed_event_count == 0


def test_arpeggio_filter_keeps_three_sustained_parallel_slots_per_cycle() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    parallel = (60, 67, 72)
    events = []
    for index, primary in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.2, primary, 90, 0.9))
        slot = index % len(pattern)
        if slot < len(parallel):
            events.append(NoteEvent(start, start + 0.4, parallel[slot], 88, 0.88))

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 6.0),))

    assert len(result.events) == 33
    assert sum(event.velocity == 88 for event in result.events) == 9
    assert result.removed_event_count == 0


def test_repeated_arpeggio_does_not_stabilize_an_unrelated_tail() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.2, pitch, 90, 0.9)
        for index, pitch in enumerate(pattern * 3)
    ]
    events.extend(
        (
            NoteEvent(10, 10.5, 48, 90, 0.9),
            NoteEvent(10, 10.4, 72, 90, 0.9),
            NoteEvent(11, 11.5, 55, 90, 0.9),
            NoteEvent(11, 11.4, 65, 90, 0.9),
        )
    )

    result = assign_hands(events)
    tail = [event for event in result.events if event.start_sec >= 10]

    assert result.strategy == "simple_arpeggio_stable_zone"
    assert any(event.hand is None for event in tail)
    assert all((event.hand_confidence or 0.0) < 0.92 for event in tail)


def test_voice_assignment_never_overlaps_within_a_voice() -> None:
    groups = [
        NotationGroup(0, 8, (60,), 90, 0.9),
        NotationGroup(2, 4, (64,), 90, 0.9),
        NotationGroup(4, 6, (67,), 90, 0.9),
    ]

    voices = assign_voices(groups)

    assert len(voices) == 2
    assert all(
        left.end_units <= right.start_units
        for voice in voices
        for left, right in zip(voice, voice[1:], strict=False)
    )


def test_voicing_config_version_changes_with_threshold() -> None:
    assert VoicingConfig().version.startswith("voicing-v4/")
    assert VoicingConfig().version != VoicingConfig(minimum_confidence=0.3).version
