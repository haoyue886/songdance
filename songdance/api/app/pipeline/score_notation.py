from fractions import Fraction

from music21 import chord, expressions, note, stream

from app.pipeline.harmony import group_harmony
from app.pipeline.quantize import GRID_DIVISIONS
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
    for voice_index, voice_groups in enumerate(assign_voices(compression.groups), start=1):
        notation_voice = stream.Voice(id=f"{hand}-voice-{voice_index}")
        for group in voice_groups:
            duration = Fraction(group.end_units - group.start_units, GRID_DIVISIONS)
            if len(group.pitches) == 1:
                notation = note.Note(group.pitches[0], quarterLength=duration)
            else:
                notation = chord.Chord(group.pitches, quarterLength=duration)
            notation.volume.velocity = group.velocity
            notation_voice.insert(Fraction(group.start_units, GRID_DIVISIONS), notation)
        part.insert(0, notation_voice)
    return compression.summary()


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
    }


def apply_cc64_pedal_marks(
    score: stream.Score,
    evidence: SustainEvidence | None,
    seconds_per_quarter: float,
    measure_offset_units: int,
) -> int:
    if evidence is None or not evidence.cc64_intervals:
        return 0

    anchors = sorted(
        (
            (float(item.getOffsetInHierarchy(score)), item)
            for item in score.recurse().notes
        ),
        key=lambda pair: pair[0],
    )
    if len(anchors) < 2:
        return 0

    applied = 0
    offset_quarters = measure_offset_units / GRID_DIVISIONS
    for start_seconds, end_seconds in evidence.cc64_intervals:
        start_quarters = start_seconds / seconds_per_quarter + offset_quarters
        end_quarters = end_seconds / seconds_per_quarter + offset_quarters
        start_anchor = _first_anchor_at_or_after(anchors, start_quarters)
        end_anchor = _first_anchor_at_or_after(anchors, end_quarters)
        if end_anchor is None:
            end_anchor = _last_anchor_at_or_before(anchors, end_quarters)
        if start_anchor is None or end_anchor is None or start_anchor is end_anchor:
            continue
        pedal = expressions.PedalMark(start_anchor, end_anchor)
        pedal.pedalType = expressions.PedalType.Sustain
        pedal.pedalForm = expressions.PedalForm.Line
        pedal.placement = "below"
        score.insert(0, pedal)
        applied += 1
    return applied


def _first_anchor_at_or_after(
    anchors: list[tuple[float, note.GeneralNote]], position: float
) -> note.GeneralNote | None:
    return next((item for offset, item in anchors if offset >= position), None)


def _last_anchor_at_or_before(
    anchors: list[tuple[float, note.GeneralNote]], position: float
) -> note.GeneralNote | None:
    return next((item for offset, item in reversed(anchors) if offset <= position), None)
