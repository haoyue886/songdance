from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from music21 import (
    chord,
    clef,
    instrument,
    key,
    metadata,
    meter,
    note,
    stream,
    tempo,
)
from music21.exceptions21 import Music21Exception

from app.pipeline.analysis import AnalysisConfig, StructureAnalysis, fallback_analysis
from app.pipeline.errors import ScoreGenerationError
from app.pipeline.harmony import HarmonyConfig, group_harmony
from app.pipeline.quantize import (
    GRID_DIVISIONS,
    notation_measure_offset_units,
    quantize_events,
    seconds_per_quarter,
)
from app.pipeline.score_validation import (
    raise_for_structure_errors,
    score_structure_summary,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voicing import (
    UNKNOWN_HAND_NOTATION_FALLBACK,
    VoicingConfig,
    assign_hands,
    assign_voices,
    notation_hand,
)

POSTPROCESS_VERSION = (
    "music21-10.5.0/beat-grid/pickup-v2/"
    f"{HarmonyConfig().version}/{VoicingConfig().version}"
)
TIME_SIGNATURE_ASSUMED = "TIME_SIGNATURE_ASSUMED_4_4"
HAND_ASSIGNMENT_INFERRED = "HAND_ASSIGNMENT_INFERRED"
SCORE_RECONSTRUCTION_FALLBACK = "SCORE_RECONSTRUCTION_FALLBACK"
STRUCTURE_ANALYSIS_NOT_RUN = "STRUCTURE_ANALYSIS_NOT_RUN"
RECOVERABLE_SCORE_ERRORS = (ValueError, Music21Exception)


@dataclass(frozen=True)
class ScoredTranscription:
    score: stream.Score
    notes: list[NoteEvent]
    tempo_bpm: float
    quality_flags: list[str]
    analysis: StructureAnalysis
    reconstruction: dict[str, object]


def build_score(
    events: list[NoteEvent],
    title: str = "SongDance Transcription",
    analysis: StructureAnalysis | None = None,
) -> ScoredTranscription:
    active_analysis = analysis or fallback_analysis(
        AnalysisConfig(), STRUCTURE_ANALYSIS_NOT_RUN, source="score_default"
    )
    flags = [*active_analysis.reason_codes, HAND_ASSIGNMENT_INFERRED]
    if active_analysis.time_signature_source == "default":
        flags.append(TIME_SIGNATURE_ASSUMED)
    quantized = quantize_events(events, active_analysis)
    voicing = assign_hands(quantized)
    if voicing.unknown_count:
        flags.append(UNKNOWN_HAND_NOTATION_FALLBACK)
    quarter_seconds = seconds_per_quarter(active_analysis)
    measure_offset_units = notation_measure_offset_units(active_analysis)

    try:
        score, structure = _build_reconstructed_score(
            voicing.events,
            title,
            active_analysis,
            quarter_seconds,
            measure_offset_units,
        )
        reconstruction = {
            "status": "reconstructed",
            "version": POSTPROCESS_VERSION,
            "fallback_used": False,
            "error_code": None,
            "voicing": voicing.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
        }
    except RECOVERABLE_SCORE_ERRORS as error:
        try:
            score, structure = _build_basic_score(
                voicing.events,
                title,
                active_analysis,
                quarter_seconds,
                measure_offset_units,
            )
        except RECOVERABLE_SCORE_ERRORS as fallback_error:
            raise ScoreGenerationError() from fallback_error
        flags.append(SCORE_RECONSTRUCTION_FALLBACK)
        reconstruction = {
            "status": "fallback",
            "version": POSTPROCESS_VERSION,
            "fallback_used": True,
            "error_code": "SCORE_RECONSTRUCTION_FAILED",
            "detail": type(error).__name__,
            "voicing": voicing.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
        }
    return ScoredTranscription(
        score, voicing.events, active_analysis.bpm, flags, active_analysis, reconstruction
    )


def _build_reconstructed_score(
    events: list[NoteEvent],
    title: str,
    analysis: StructureAnalysis,
    quarter_seconds: float,
    measure_offset_units: int,
) -> tuple[stream.Score, dict[str, object]]:
    score = stream.Score(id="songdance-score")
    score.metadata = metadata.Metadata(title=title)
    right = _new_part("right-hand", "Piano · Right Hand", clef.TrebleClef(), analysis)
    left = _new_part("left-hand", "Piano · Left Hand", clef.BassClef(), analysis)
    _populate_part(right, events, "right", quarter_seconds, measure_offset_units)
    _populate_part(left, events, "left", quarter_seconds, measure_offset_units)
    score.insert(0, right)
    score.insert(0, left)
    return _finalize_score(score, measure_offset_units)


def _build_basic_score(
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
    _apply_pickup_measures(score, measure_offset_units)
    raise_for_structure_errors(score, validate_measure_durations=True)
    return score, score_structure_summary(score, validate_measure_durations=True)

def _apply_pickup_measures(score: stream.Score, measure_offset_units: int) -> None:
    if measure_offset_units <= 0:
        return
    padding = Fraction(measure_offset_units, GRID_DIVISIONS)
    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            continue
        first = measures[0]
        if list(first.recurse().notes):
            containers = list(first.getElementsByClass(stream.Voice)) or [first]
            for container in containers:
                _trim_pickup_padding(container, padding)
        else:
            for rest in list(first.recurse().getElementsByClass(note.Rest)):
                first.remove(rest, recurse=True)
            first.insert(0, note.Rest(quarterLength=first.barDuration.quarterLength - padding))
        first.paddingLeft = padding

def _trim_pickup_padding(container: stream.Stream, padding: Fraction) -> None:
    for element in list(container.notesAndRests):
        start = Fraction(element.offset)
        end = start + Fraction(element.quarterLength)
        if end <= padding:
            container.remove(element)
        elif start < padding:
            container.setElementOffset(element, 0)
            element.quarterLength = end - padding
        else:
            container.setElementOffset(element, start - padding)


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


def _populate_part(
    part: stream.Part,
    events: list[NoteEvent],
    hand: str,
    seconds_per_quarter: float,
    measure_offset_units: int,
) -> None:
    groups = group_harmony(
        [event for event in events if notation_hand(event) == hand],
        seconds_per_quarter,
        measure_offset_units,
    )
    for voice_index, voice_groups in enumerate(assign_voices(groups), start=1):
        notation_voice = stream.Voice(id=f"{hand}-voice-{voice_index}")
        for group in voice_groups:
            duration = Fraction(group.end_units - group.start_units, GRID_DIVISIONS)
            if len(group.pitches) == 1:
                notation = note.Note(group.pitches[0], quarterLength=duration)
            else:
                notation = chord.Chord(group.pitches, quarterLength=duration)
            notation.volume.velocity = group.velocity
            notation_voice.insert(
                Fraction(group.start_units, GRID_DIVISIONS),
                notation,
            )
        part.insert(0, notation_voice)


def write_quantized_midi(scored: ScoredTranscription, destination: Path) -> None:
    try:
        scored.score.write("midi", fp=str(destination))
    except Exception as error:
        raise ScoreGenerationError("量化 MIDI 生成失败") from error


def write_musicxml(scored: ScoredTranscription, destination: Path) -> None:
    try:
        scored.score.write("musicxml", fp=str(destination))
        read_musicxml_structure(destination)
    except Exception as error:
        raise ScoreGenerationError("MusicXML 生成失败") from error
def read_musicxml_structure(source: Path) -> dict[str, object]:
    from music21 import converter

    parsed = converter.parse(str(source))
    raise_for_structure_errors(parsed, validate_measure_durations=True)
    return score_structure_summary(parsed, validate_measure_durations=True)
