from app.pipeline.harmony import HarmonyConfig, NotationGroup, group_harmony
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voicing import VoicingConfig, assign_hands, assign_voices


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
    assert VoicingConfig().version != VoicingConfig(minimum_confidence=0.3).version
