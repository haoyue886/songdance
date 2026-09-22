from fractions import Fraction

from music21 import (
    clef,
    dynamics,
    instrument,
    key,
    layout,
    metadata,
    meter,
    note,
    pitch,
    stream,
    tempo,
)

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.harmony import HarmonyConfig, group_harmony
from app.pipeline.pickup import apply_pickup_measures
from app.pipeline.quantize import integer_tempo_bpm
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

VOICE_REST_PRUNING_VERSION = "voice-rest-pruning-v1"


def build_reconstructed_score(
    events: list[NoteEvent],
    title: str,
    analysis: StructureAnalysis,
    quarter_seconds: float,
    measure_offset_units: int,
    sustain_evidence: SustainEvidence | None,
    divisions_per_quarter: int,
    *,
    collapse_to_single_voice: bool,
    with_mp: bool,
    single_staff: bool = False,
) -> tuple[stream.Score, dict[str, object], dict[str, object]]:
    score = stream.Score(id="songdance-score")
    score.metadata = _score_metadata(title)
    if single_staff and any(notation_hand(event) != "right" for event in events):
        raise ValueError("SINGLE_STAFF_REQUIRES_TREBLE_EVENTS")
    right = _new_staff(
        "right-hand", clef.TrebleClef(), analysis, with_tempo=True,
        single_staff=single_staff,
    )
    left = _new_staff("left-hand", clef.BassClef(), analysis)
    right_compression = populate_part(
        right,
        events,
        "right",
        quarter_seconds,
        measure_offset_units,
        sustain_evidence,
        divisions_per_quarter,
        collapse_to_single_voice=collapse_to_single_voice,
    )
    left_compression = populate_part(
        left,
        events,
        "left",
        quarter_seconds,
        measure_offset_units,
        sustain_evidence,
        divisions_per_quarter,
        collapse_to_single_voice=collapse_to_single_voice,
    )
    score.insert(0, right)
    if not single_staff:
        score.insert(0, left)
        _insert_piano_staff_group(score, right, left)
    if collapse_to_single_voice:
        single_voice_applied = bool(
            right_compression["single_voice_applied"] and left_compression["single_voice_applied"]
        )
        raise_for_piano_staff_layout(score, max_voices=1 if single_voice_applied else None)
    score, structure = _finalize_score(
        score,
        measure_offset_units,
        divisions_per_quarter,
        with_mp=with_mp,
    )
    pedal_marking_count = apply_sustain_pedal_marks(
        score,
        sustain_evidence,
        quarter_seconds,
        measure_offset_units,
        divisions_per_quarter,
    )
    compression = combined_compression_summary(
        right_compression,
        left_compression,
        sustain_evidence,
        pedal_marking_count,
    )
    compression["pruned_inactive_voice_count"] = structure[
        "pruned_inactive_voice_count"
    ]
    return score, structure, compression


def build_basic_score(
    events: list[NoteEvent],
    title: str,
    analysis: StructureAnalysis,
    quarter_seconds: float,
    measure_offset_units: int,
    divisions_per_quarter: int,
    *,
    with_mp: bool = False,
    single_staff: bool = False,
) -> tuple[stream.Score, dict[str, object]]:
    if single_staff and any(notation_hand(event) != "right" for event in events):
        raise ValueError("SINGLE_STAFF_REQUIRES_TREBLE_EVENTS")
    score = stream.Score(id="songdance-score-fallback")
    score.metadata = _score_metadata(title)
    staffs = []
    for hand, part_id, staff_clef in (
        ("right", "right-hand", clef.TrebleClef()),
        ("left", "left-hand", clef.BassClef()),
    ):
        if single_staff and hand == "left":
            continue
        part = _new_staff(
            part_id,
            staff_clef,
            analysis,
            with_tempo=hand == "right",
            single_staff=single_staff,
        )
        candidates = group_harmony(
            [event for event in events if notation_hand(event) == hand],
            quarter_seconds,
            measure_offset_units,
            HarmonyConfig(maximum_chord_size=1, duration_tolerance_units=0),
            divisions_per_quarter=divisions_per_quarter,
        )
        voice = stream.Voice(id=f"{hand}-fallback-voice")
        previous_end = 0
        for group in candidates:
            if group.start_units < previous_end:
                continue
            notation = note.Note(
                pitch.Pitch(midi=group.pitches[0]),
                quarterLength=Fraction(
                    group.end_units - group.start_units, divisions_per_quarter
                ),
            )
            notation.volume.velocity = group.velocity
            voice.insert(Fraction(group.start_units, divisions_per_quarter), notation)
            previous_end = group.end_units
        part.insert(0, voice)
        score.insert(0, part)
        staffs.append(part)
    if not single_staff:
        _insert_piano_staff_group(score, *staffs)
    return _finalize_score(
        score, measure_offset_units, divisions_per_quarter, with_mp=with_mp
    )


def _finalize_score(
    score: stream.Score,
    measure_offset_units: int,
    divisions_per_quarter: int,
    *,
    with_mp: bool = False,
) -> tuple[stream.Score, dict[str, object]]:
    raise_for_piano_staff_layout(score, max_voices=None)
    raise_for_structure_errors(score)
    _fill_voice_gaps(score)
    score.makeNotation(inPlace=True)
    apply_pickup_measures(score, measure_offset_units, divisions_per_quarter)
    pruned_voice_count = _prune_inactive_measure_voices(score)
    if with_mp:
        _insert_initial_mp(score)
    raise_for_structure_errors(score, validate_measure_durations=True)
    summary = score_structure_summary(score, validate_measure_durations=True)
    summary["pruned_inactive_voice_count"] = pruned_voice_count
    return score, summary


def _score_metadata(title: str) -> metadata.Metadata:
    score_metadata = metadata.Metadata()
    score_metadata.movementName = title
    score_metadata.composer = ""
    return score_metadata


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


def _prune_inactive_measure_voices(score: stream.Score) -> int:
    removed = 0
    for measure in list(score.recurse().getElementsByClass(stream.Measure)):
        if Fraction(measure.paddingLeft) > 0:
            continue
        voices = list(measure.getElementsByClass(stream.Voice))
        active = [voice for voice in voices if list(voice.notes)]
        inactive = [voice for voice in voices if voice not in active]
        target_duration = Fraction(measure.barDuration.quarterLength) - Fraction(
            measure.paddingLeft
        )
        active_fills_measure = any(
            Fraction(voice.lowestOffset) == 0
            and Fraction(voice.highestTime) >= target_duration
            for voice in active
        )
        keep = set(active)
        if inactive and (not active or not active_fills_measure):
            keep.add(inactive[0])
        for notation_voice in voices:
            if notation_voice not in keep:
                measure.remove(notation_voice)
                removed += 1
    return removed


def _new_staff(
    part_id: str,
    staff_clef: clef.Clef,
    analysis: StructureAnalysis,
    *,
    with_tempo: bool = False,
    single_staff: bool = False,
) -> stream.Part:
    part = stream.Part(id=part_id) if single_staff else stream.PartStaff(id=part_id)
    part.partName = "Piano"
    part.insert(0, instrument.Piano())
    part.insert(0, staff_clef)
    tonic, mode = analysis.key_signature.split(" ", 1)
    part.insert(0, meter.TimeSignature(analysis.time_signature))
    part.insert(0, key.Key(tonic, mode))
    if with_tempo:
        part.insert(0, tempo.MetronomeMark(number=integer_tempo_bpm(analysis.bpm)))
    return part


def _insert_initial_mp(score: stream.Score) -> None:
    marking = dynamics.Dynamic("mp")
    marking.placement = "below"
    first_measure = next(iter(score.parts[0].getElementsByClass(stream.Measure)))
    first_measure.insert(0, marking)


def _insert_piano_staff_group(
    score: stream.Score, right: stream.PartStaff, left: stream.PartStaff
) -> None:
    score.insert(
        0,
        layout.StaffGroup(
            [right, left],
            name="Piano",
            abbreviation="Pno.",
            symbol="brace",
            barTogether=True,
        ),
    )
