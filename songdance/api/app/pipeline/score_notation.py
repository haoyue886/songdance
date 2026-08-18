from bisect import bisect_right
from fractions import Fraction

from music21 import chord, expressions, note, pitch, stream

from app.pipeline.harmony import NotationGroup, group_harmony
from app.pipeline.quantize import GRID_DIVISIONS
from app.pipeline.simple_arpeggio import SIMPLE_ARPEGGIO_PATTERN
from app.pipeline.sustain import SustainEvidence
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voice_compression import (
    VoiceCompressionConfig,
    compress_notation_durations,
)
from app.pipeline.voicing import assign_voices, notation_hand


def populate_part(
    part: stream.Part,
    events: list[NoteEvent],
    hand: str,
    seconds_per_quarter: float,
    measure_offset_units: int,
    sustain_evidence: SustainEvidence | None,
    *,
    collapse_to_single_voice: bool = False,
) -> dict[str, object]:
    groups = group_harmony(
        [event for event in events if notation_hand(event) == hand],
        seconds_per_quarter,
        measure_offset_units,
    )
    compression = compress_notation_durations(
        groups,
        seconds_per_quarter,
        measure_offset_units,
        sustain_evidence,
    )
    notation_groups = compression.groups
    collapsed = False
    if collapse_to_single_voice:
        global_groups = group_harmony(
            events,
            seconds_per_quarter,
            measure_offset_units,
        )
        notation_groups, collapsed = _collapse_to_single_voice(notation_groups, global_groups)
    voices = [notation_groups] if collapsed else assign_voices(notation_groups)
    if not voices:
        voices = [[]]
    for voice_index, voice_groups in enumerate(voices, start=1):
        notation_voice = stream.Voice(id=f"{hand}-voice-{voice_index}")
        for group in voice_groups:
            duration = Fraction(group.end_units - group.start_units, GRID_DIVISIONS)
            if len(group.pitches) == 1:
                notation = note.Note(pitch.Pitch(midi=group.pitches[0]), quarterLength=duration)
            else:
                notation = chord.Chord(
                    [pitch.Pitch(midi=value) for value in group.pitches],
                    quarterLength=duration,
                )
            notation.volume.velocity = group.velocity
            notation_voice.insert(Fraction(group.start_units, GRID_DIVISIONS), notation)
        part.insert(0, notation_voice)
    summary = compression.summary()
    summary.update(
        {
            "notation_voice_count": len(voices),
            "single_voice_requested": collapse_to_single_voice,
            "single_voice_applied": collapsed,
        }
    )
    return summary


def _collapse_to_single_voice(
    groups: list[NotationGroup],
    global_groups: list[NotationGroup],
) -> tuple[list[NotationGroup], bool]:
    """Flatten resonant arpeggio groups without discarding simultaneous pitches."""
    if not groups:
        return groups, True
    independent = _independent_polyphony_groups(groups, global_groups)
    collapsible = [group for group in groups if group not in independent]

    by_start: dict[int, list[NotationGroup]] = {}
    for group in collapsible:
        by_start.setdefault(group.start_units, []).append(group)
    if any(
        len({pitch for group in start_groups for pitch in group.pitches})
        > VoiceCompressionConfig().maximum_chord_size
        for start_groups in by_start.values()
    ):
        return groups, False

    global_onsets = sorted({group.start_units for group in global_groups})
    starts = sorted(by_start)
    flattened = []
    for index, start in enumerate(starts):
        start_groups = by_start[start]
        next_onset_index = bisect_right(global_onsets, start)
        next_start = (
            global_onsets[next_onset_index] if next_onset_index < len(global_onsets) else None
        )
        if next_start is None and index + 1 < len(starts):
            next_start = starts[index + 1]
        pitches = tuple(sorted({pitch for group in start_groups for pitch in group.pitches}))
        end = max(group.end_units for group in start_groups)
        if next_start is not None:
            end = min(end, next_start)
        if end <= start:
            end = next_start or start + 1
        weight = sum(len(group.pitches) for group in start_groups)
        velocity = round(
            sum(group.velocity * len(group.pitches) for group in start_groups) / weight
        )
        confidence = round(
            sum(group.confidence * len(group.pitches) for group in start_groups) / weight,
            6,
        )
        flattened.append(
            NotationGroup(
                start_units=start,
                end_units=end,
                pitches=pitches,
                velocity=velocity,
                confidence=confidence,
            )
        )
    return sorted(
        [*independent, *flattened],
        key=lambda item: (item.start_units, -item.end_units, item.pitches),
    ), not independent


def _independent_polyphony_groups(
    groups: list[NotationGroup],
    global_groups: list[NotationGroup],
) -> set[NotationGroup]:
    config = VoiceCompressionConfig()
    independent = set()
    for group in groups:
        for note_pitch in group.pitches:
            onset_pitches = {
                candidate_pitch
                for candidate in global_groups
                if candidate.start_units == group.start_units
                for candidate_pitch in candidate.pitches
            }
            if note_pitch in SIMPLE_ARPEGGIO_PATTERN and onset_pitches == {note_pitch}:
                continue
            separated_onsets = {
                candidate.start_units
                for candidate in global_groups
                if group.start_units < candidate.start_units < group.end_units
                and all(
                    abs(note_pitch - other_pitch) >= config.minimum_independent_pitch_separation
                    for other_pitch in candidate.pitches
                )
            }
            if len(separated_onsets) >= config.minimum_independent_overlap_onsets:
                independent.add(group)
                break
    return independent


def combined_compression_summary(
    right: dict[str, object],
    left: dict[str, object],
    evidence: SustainEvidence | None,
    pedal_marking_count: int,
) -> dict[str, object]:
    active_evidence = evidence or SustainEvidence.unavailable()
    reasons = sorted({*right["reason_codes"], *left["reason_codes"]})
    return {
        "version": VoiceCompressionConfig().version,
        "applied": bool(right["applied"] or left["applied"]),
        "compressed_group_count": int(right["compressed_group_count"])
        + int(left["compressed_group_count"]),
        "coalesced_group_count": int(right["coalesced_group_count"])
        + int(left["coalesced_group_count"]),
        "dense_run_count": int(right["dense_run_count"]) + int(left["dense_run_count"]),
        "reason_codes": tuple(reasons),
        "evidence": active_evidence.summary(),
        "pedal_marking_applied": pedal_marking_count > 0,
        "pedal_marking_count": pedal_marking_count,
        "notation_voice_count": max(
            int(right.get("notation_voice_count", 0)),
            int(left.get("notation_voice_count", 0)),
        ),
        "single_voice_applied": bool(
            right.get("single_voice_applied") and left.get("single_voice_applied")
        ),
    }


def apply_sustain_pedal_marks(
    score: stream.Score,
    evidence: SustainEvidence | None,
    seconds_per_quarter: float,
    measure_offset_units: int,
) -> int:
    if evidence is None:
        return 0

    intervals = _merge_pedal_intervals((*evidence.cc64_intervals, *evidence.audio_pedal_intervals))
    if not intervals:
        return 0

    anchors_by_staff = [
        sorted(
            ((float(item.getOffsetInHierarchy(score)), item) for item in part.recurse().notes),
            key=lambda pair: pair[0],
        )
        for part in reversed(score.parts)
    ]
    if not any(len(anchors) >= 2 for anchors in anchors_by_staff):
        return 0

    applied = 0
    offset_quarters = measure_offset_units / GRID_DIVISIONS
    for start_seconds, end_seconds in intervals:
        start_quarters = start_seconds / seconds_per_quarter + offset_quarters
        end_quarters = end_seconds / seconds_per_quarter + offset_quarters
        anchors = next(
            (
                pair
                for staff_anchors in anchors_by_staff
                if (pair := _pedal_anchor_pair(staff_anchors, start_quarters, end_quarters))
                is not None
            ),
            None,
        )
        if anchors is None:
            continue
        start_anchor, end_anchor = anchors
        pedal = expressions.PedalMark(start_anchor, end_anchor)
        pedal.pedalType = expressions.PedalType.Sustain
        pedal.pedalForm = expressions.PedalForm.Line
        pedal.placement = "below"
        score.insert(0, pedal)
        applied += 1
    return applied


def _pedal_anchor_pair(
    anchors: list[tuple[float, note.GeneralNote]], start: float, end: float
) -> tuple[note.GeneralNote, note.GeneralNote] | None:
    start_anchor = _first_anchor_at_or_after(anchors, start)
    end_anchor = _first_anchor_at_or_after(anchors, end)
    if end_anchor is None:
        end_anchor = _last_anchor_at_or_before(anchors, end)
    if start_anchor is None or end_anchor is None or start_anchor is end_anchor:
        return None
    return start_anchor, end_anchor


def _merge_pedal_intervals(
    intervals: tuple[tuple[float, float], ...],
) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _first_anchor_at_or_after(
    anchors: list[tuple[float, note.GeneralNote]], position: float
) -> note.GeneralNote | None:
    return next((item for offset, item in anchors if offset >= position), None)


def _last_anchor_at_or_before(
    anchors: list[tuple[float, note.GeneralNote]], position: float
) -> note.GeneralNote | None:
    return next((item for offset, item in reversed(anchors) if offset <= position), None)
