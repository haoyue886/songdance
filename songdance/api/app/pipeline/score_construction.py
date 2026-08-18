from fractions import Fraction

from music21 import clef, instrument, key, metadata, meter, note, stream, tempo

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.harmony import HarmonyConfig, group_harmony
from app.pipeline.pickup import apply_pickup_measures
from app.pipeline.quantize import GRID_DIVISIONS
from app.pipeline.score_notation import (
    apply_sustain_pedal_marks,
    combined_compression_summary,
    populate_part,
)
from app.pipeline.score_validation import (
    raise_for_piano_staff_layout,
    raise_for_structure_errors,
    score_structure_summary,
)
from app.pipeline.sustain import SustainEvidence
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voicing import notation_hand


def build_reconstructed_score(
    events: list[NoteEvent],
    title: str,
    analysis: StructureAnalysis,
    quarter_seconds: float,
    measure_offset_units: int,
    sustain_evidence: SustainEvidence | None,
    *,
    collapse_to_single_voice: bool,
) -> tuple[stream.Score, dict[str, object], dict[str, object]]:
    score = stream.Score(id="songdance-score")
    score.metadata = metadata.Metadata(title=title)
    right = _new_part("right-hand", "Piano · Right Hand", clef.TrebleClef(), analysis)
    left = _new_part("left-hand", "Piano · Left Hand", clef.BassClef(), analysis)
    right_compression = populate_part(
        right,
        events,
        "right",
        quarter_seconds,
        measure_offset_units,
        sustain_evidence,
        collapse_to_single_voice=collapse_to_single_voice,
    )
    left_compression = populate_part(
        left,
        events,
        "left",
        quarter_seconds,
        measure_offset_units,
        sustain_evidence,
        collapse_to_single_voice=collapse_to_single_voice,
    )
    score.insert(0, right)
    score.insert(0, left)
    if collapse_to_single_voice:
        single_voice_applied = bool(
            right_compression["single_voice_applied"]
            and left_compression["single_voice_applied"]
        )
        raise_for_piano_staff_layout(
            score, max_voices=1 if single_voice_applied else None
        )
    score, structure = _finalize_score(score, measure_offset_units)
    pedal_marking_count = apply_sustain_pedal_marks(
        score,
        sustain_evidence,
        quarter_seconds,
        measure_offset_units,
    )
    compression = combined_compression_summary(
        right_compression,
        left_compression,
        sustain_evidence,
        pedal_marking_count,
    )
    return score, structure, compression


def build_basic_score(
    events: list[NoteEvent],
    title: str,
    analysis: StructureAnalysis,
    quarter_seconds: float,
    measure_offset_units: int,
) -> tuple[stream.Score, dict[str, object]]:
    score = stream.Score(id="songdance-score-fallback")
    score.metadata = metadata.Metadata(title=title)
    for hand, part_id, name, staff_clef in (
        ("right", "right-hand", "Piano · Right Hand", clef.TrebleClef()),
        ("left", "left-hand", "Piano · Left Hand", clef.BassClef()),
    ):
        part = _new_part(part_id, name, staff_clef, analysis)
        candidates = group_harmony(
            [event for event in events if notation_hand(event) == hand],
            quarter_seconds,
            measure_offset_units,
            HarmonyConfig(maximum_chord_size=1, duration_tolerance_units=0),
        )
        voice = stream.Voice(id=f"{hand}-fallback-voice")
        previous_end = 0
        for group in candidates:
            if group.start_units < previous_end:
                continue
            notation = note.Note(
                group.pitches[0],
                quarterLength=Fraction(
                    group.end_units - group.start_units, GRID_DIVISIONS
                ),
            )
            notation.volume.velocity = group.velocity
            voice.insert(Fraction(group.start_units, GRID_DIVISIONS), notation)
            previous_end = group.end_units
        part.insert(0, voice)
        score.insert(0, part)
    return _finalize_score(score, measure_offset_units)


def _finalize_score(
    score: stream.Score, measure_offset_units: int
) -> tuple[stream.Score, dict[str, object]]:
    raise_for_structure_errors(score)
    _fill_voice_gaps(score)
    score.makeNotation(inPlace=True)
    apply_pickup_measures(score, measure_offset_units)
    raise_for_structure_errors(score, validate_measure_durations=True)
    return score, score_structure_summary(score, validate_measure_durations=True)


def _fill_voice_gaps(score: stream.Score) -> None:
    score_end = score.highestTime
    for part in score.parts:
        voices = list(part.getElementsByClass(stream.Voice))
        for index, notation_voice in enumerate(voices):
            start = 0 if index == 0 else notation_voice.lowestOffset
            end = score_end if index == 0 else notation_voice.highestTime
            notation_voice.makeRests(
                refStreamOrTimeRange=(start, end),
                fillGaps=True,
                inPlace=True,
            )


def _new_part(
    part_id: str,
    name: str,
    staff_clef: clef.Clef,
    analysis: StructureAnalysis,
) -> stream.Part:
    part = stream.Part(id=part_id)
    part.partName = name
    part.insert(0, instrument.Piano())
    part.insert(0, staff_clef)
    tonic, mode = analysis.key_signature.split(" ", 1)
    part.insert(0, meter.TimeSignature(analysis.time_signature))
    part.insert(0, key.Key(tonic, mode))
    part.insert(0, tempo.MetronomeMark(number=analysis.bpm))
    return part
