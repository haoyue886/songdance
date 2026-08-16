from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from music21 import (
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
from app.pipeline.pickup import apply_pickup_measures
from app.pipeline.quantize import (
    GRID_DIVISIONS,
    decide_notation_pickup,
    quantize_events,
    seconds_per_quarter,
)
from app.pipeline.score_notation import (
    apply_cc64_pedal_marks,
    combined_compression_summary,
    populate_part,
)
from app.pipeline.score_validation import (
    raise_for_structure_errors,
    score_structure_summary,
)
from app.pipeline.sustain import (
    SUSTAIN_EVIDENCE_UNAVAILABLE,
    SustainEvidence,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voice_compression import VoiceCompressionConfig
from app.pipeline.voicing import (
    UNKNOWN_HAND_NOTATION_FALLBACK,
    VoicingConfig,
    assign_hands,
    notation_hand,
)

POSTPROCESS_VERSION = (
    "music21-10.5.0/beat-grid/pickup-v4/"
    f"{HarmonyConfig().version}/{VoicingConfig().version}/{VoiceCompressionConfig().version}"
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
    sustain_evidence: SustainEvidence | None = None,
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
    pickup = decide_notation_pickup(quantized, active_analysis)
    measure_offset_units = pickup.measure_offset_units
    if sustain_evidence is None or sustain_evidence.status != "available":
        flags.append(SUSTAIN_EVIDENCE_UNAVAILABLE)

    try:
        score, structure, compression = _build_reconstructed_score(
            voicing.events,
            title,
            active_analysis,
            quarter_seconds,
            measure_offset_units,
            sustain_evidence,
        )
        reconstruction = {
            "status": "reconstructed",
            "version": POSTPROCESS_VERSION,
            "fallback_used": False,
            "error_code": None,
            "voicing": voicing.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
            "pickup": pickup.summary(),
            "voice_compression": compression,
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
            "pickup": pickup.summary(),
            "voice_compression": {
                "version": VoiceCompressionConfig().version,
                "applied": False,
                "compressed_group_count": 0,
                "coalesced_group_count": 0,
                "dense_run_count": 0,
                "reason_codes": ("SCORE_RECONSTRUCTION_FAILED",),
                "evidence": (sustain_evidence or SustainEvidence.unavailable()).summary(),
                "pedal_marking_applied": False,
                "pedal_marking_count": 0,
            },
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
    sustain_evidence: SustainEvidence | None,
) -> tuple[stream.Score, dict[str, object], dict[str, object]]:
    score = stream.Score(id="songdance-score")
    score.metadata = metadata.Metadata(title=title)
    right = _new_part("right-hand", "Piano · Right Hand", clef.TrebleClef(), analysis)
    left = _new_part("left-hand", "Piano · Left Hand", clef.BassClef(), analysis)
    right_compression = populate_part(
        right, events, "right", quarter_seconds, measure_offset_units, sustain_evidence
    )
    left_compression = populate_part(
        left, events, "left", quarter_seconds, measure_offset_units, sustain_evidence
    )
    score.insert(0, right)
    score.insert(0, left)
    score, structure = _finalize_score(score, measure_offset_units)
    pedal_marking_count = apply_cc64_pedal_marks(
        score, sustain_evidence, quarter_seconds, measure_offset_units
    )
    compression = combined_compression_summary(
        right_compression,
        left_compression,
        sustain_evidence,
        pedal_marking_count,
    )
    return score, structure, compression


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
                quarterLength=Fraction(group.end_units - group.start_units, GRID_DIVISIONS),
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
