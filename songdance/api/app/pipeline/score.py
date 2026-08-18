from dataclasses import dataclass

from music21 import stream
from music21.exceptions21 import Music21Exception

from app.pipeline.analysis import AnalysisConfig, StructureAnalysis, fallback_analysis
from app.pipeline.arpeggio_resonance import (
    SIMPLE_ARPEGGIO_FILTER_VERSION,
    filter_simple_arpeggio_resonance,
)
from app.pipeline.errors import ScoreGenerationError
from app.pipeline.harmony import HarmonyConfig
from app.pipeline.quantize import (
    FALSE_PICKUP_REJECTED_FULL_MEASURE,
    align_repeating_eighth_note_cycles,
    decide_notation_pickup,
    quantize_events,
    seconds_per_quarter,
)
from app.pipeline.score_construction import (
    build_basic_score as _build_basic_score,
)
from app.pipeline.score_construction import (
    build_reconstructed_score as _build_reconstructed_score,
)
from app.pipeline.score_io import (
    read_musicxml_structure as read_musicxml_structure,
)
from app.pipeline.score_io import (
    write_musicxml as write_musicxml,
)
from app.pipeline.score_io import (
    write_quantized_midi as write_quantized_midi,
)
from app.pipeline.sustain import (
    AUDIO_SUSTAIN_PEDAL,
    MIDI_CC64,
    SUSTAIN_EVIDENCE_UNAVAILABLE,
    SustainEvidence,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voice_compression import VoiceCompressionConfig
from app.pipeline.voicing import (
    UNKNOWN_HAND_NOTATION_FALLBACK,
    VoicingConfig,
    assign_hands,
)

POSTPROCESS_VERSION = (
    "music21-10.5.0/beat-grid/pickup-v4/"
    f"{HarmonyConfig().version}/{VoicingConfig().version}/{VoiceCompressionConfig().version}/"
    f"{SIMPLE_ARPEGGIO_FILTER_VERSION}"
)
EIGHTH_CYCLE_ALIGNMENT_VERSION = "eighth-cycle-alignment-v2"
TIME_SIGNATURE_ASSUMED = "TIME_SIGNATURE_ASSUMED_4_4"
HAND_ASSIGNMENT_INFERRED = "HAND_ASSIGNMENT_INFERRED"
SCORE_RECONSTRUCTION_FALLBACK = "SCORE_RECONSTRUCTION_FALLBACK"
STRUCTURE_ANALYSIS_NOT_RUN = "STRUCTURE_ANALYSIS_NOT_RUN"
RECOVERABLE_SCORE_ERRORS = (ValueError, Music21Exception)


@dataclass(frozen=True)
class ScoredTranscription:
    score: stream.Score
    notes: list[NoteEvent]
    notation_notes: list[NoteEvent]
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
    pickup = decide_notation_pickup(quantized, active_analysis)
    notation_input = align_repeating_eighth_note_cycles(events, active_analysis, pickup)
    if notation_input is events:
        notation_input = quantized
    voicing = assign_hands(notation_input)
    arpeggio_filter = filter_simple_arpeggio_resonance(
        voicing.events,
        pedal_intervals=_notation_pedal_intervals(sustain_evidence),
    )
    notation_events = arpeggio_filter.events
    reconstruction_version = POSTPROCESS_VERSION
    if FALSE_PICKUP_REJECTED_FULL_MEASURE in pickup.reason_codes:
        reconstruction_version = f"{POSTPROCESS_VERSION}/{EIGHTH_CYCLE_ALIGNMENT_VERSION}"
    if voicing.unknown_count:
        flags.append(UNKNOWN_HAND_NOTATION_FALLBACK)
    quarter_seconds = seconds_per_quarter(active_analysis)
    measure_offset_units = pickup.measure_offset_units
    if sustain_evidence is None or sustain_evidence.status != "available":
        flags.append(SUSTAIN_EVIDENCE_UNAVAILABLE)
    collapse_to_single_voice = voicing.strategy == "simple_arpeggio_stable_zone"

    try:
        score, structure, compression = _build_reconstructed_score(
            notation_events,
            title,
            active_analysis,
            quarter_seconds,
            measure_offset_units,
            sustain_evidence,
            collapse_to_single_voice=collapse_to_single_voice,
        )
        reconstruction = {
            "status": "reconstructed",
            "version": reconstruction_version,
            "fallback_used": False,
            "error_code": None,
            "voicing": voicing.summary(),
            "arpeggio_filter": arpeggio_filter.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
            "pickup": pickup.summary(),
            "voice_compression": compression,
        }
    except RECOVERABLE_SCORE_ERRORS as error:
        try:
            score, structure = _build_basic_score(
                notation_events,
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
            "version": reconstruction_version,
            "fallback_used": True,
            "error_code": "SCORE_RECONSTRUCTION_FAILED",
            "detail": type(error).__name__,
            "voicing": voicing.summary(),
            "arpeggio_filter": arpeggio_filter.summary(),
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
        score=score,
        notes=voicing.events,
        notation_notes=notation_events,
        tempo_bpm=active_analysis.bpm,
        quality_flags=flags,
        analysis=active_analysis,
        reconstruction=reconstruction,
    )


def _notation_pedal_intervals(
    evidence: SustainEvidence | None,
) -> tuple[tuple[float, float], ...]:
    if evidence is None:
        return ()
    intervals = []
    if MIDI_CC64 in evidence.sources:
        intervals.extend(evidence.cc64_intervals)
    if AUDIO_SUSTAIN_PEDAL in evidence.sources:
        intervals.extend(evidence.audio_pedal_intervals)
    return tuple(intervals)
