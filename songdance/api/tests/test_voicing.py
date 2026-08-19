from app.pipeline.arpeggio_resonance import (
    SIMPLE_ARPEGGIO_RESONANCE_FILTERED,
    filter_simple_arpeggio_resonance,
)
from app.pipeline.harmony import HarmonyConfig, NotationGroup, group_harmony
from app.pipeline.score import build_score
from app.pipeline.simple_arpeggio import (
    SIMPLE_ARPEGGIO_APPLIED,
    SIMPLE_ARPEGGIO_CLEAR_ZONE,
    SIMPLE_ARPEGGIO_REJECTED_CROSSING,
    SIMPLE_ARPEGGIO_STABLE_TIMING,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voicing import (
    VoicingConfig,
    assign_hands,
    assign_voices,
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
    for index, pitch in enumerate(pattern * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.4, pitch, 90, 0.9))
        if index:
            previous_pitch = (pattern * 3)[index - 1]
            events.append(NoteEvent(start, start + 0.2, previous_pitch, 55, 0.4))

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 6.0),))
    filtered_pattern = [event.pitch for event in result.events if event.pitch != 36]

    assert filtered_pattern == list(pattern * 3)
    assert any(event.pitch == 36 and event.end_sec == 6.0 for event in result.events)
    assert result.applied is True
    assert result.removed_event_count == 23
    assert result.stable_cycle_count == 3
    assert result.matched_slot_count == 24
    assert result.reason_codes == (SIMPLE_ARPEGGIO_RESONANCE_FILTERED,)


def test_arpeggio_resonance_filter_requires_pedal_evidence() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.4, pitch, 90, 0.9)
        for index, pitch in enumerate(pattern * 3)
    ]
    events.append(NoteEvent(0.25, 0.5, 48, 55, 0.4))

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=())

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

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 4.0),))

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

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 8.0),))

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

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 8.0),))

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

    result = filter_simple_arpeggio_resonance(events, pedal_intervals=((0.0, 8.0),))

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
    assert VoicingConfig().version.startswith("voicing-v3/")
    assert VoicingConfig().version != VoicingConfig(minimum_confidence=0.3).version
