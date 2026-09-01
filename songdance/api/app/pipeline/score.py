from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from statistics import median

from music21 import stream
from music21.exceptions21 import Music21Exception

from app.pipeline.adaptive_quantization import (
    ADAPTIVE_QUANTIZATION_VERSION,
    QuantizationDecision,
    select_quantization,
)
from app.pipeline.analysis import AnalysisConfig, StructureAnalysis, fallback_analysis
from app.pipeline.arpeggio_resonance import (
    SIMPLE_ARPEGGIO_FILTER_VERSION,
    filter_simple_arpeggio_resonance,
)
from app.pipeline.errors import ScoreGenerationError
from app.pipeline.harmonics import HarmonicEvidence
from app.pipeline.harmony import HarmonyConfig
from app.pipeline.notation_context import NotationContext, ResolvedNotationContext
from app.pipeline.polyphony_limit import RESONANT_POLYPHONY_VERSION
from app.pipeline.quantize import (
    FALSE_PICKUP_REJECTED_FULL_MEASURE,
    PickupDecision,
    align_repeating_eighth_note_cycles,
    decide_notation_pickup,
    integer_tempo_bpm,
    quantize_events,
    seconds_per_quarter,
)
from app.pipeline.score_construction import (
    VOICE_REST_PRUNING_VERSION,
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
    read_musicxml_visible_metadata as read_musicxml_visible_metadata,
)
from app.pipeline.score_io import (
    write_musicxml as write_musicxml,
)
from app.pipeline.score_io import (
    write_quantized_midi as write_quantized_midi,
)
from app.pipeline.staff_distribution import (
    STAFF_DISTRIBUTION_SUSPECT,
    staff_distribution_summary,
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

DYNAMIC_MARKING_VERSION = "dynamic-marking-v1"
SCORE_METADATA_VERSION = "score-metadata-v1"
ORNAMENT_REVIEW_REQUIRED = "ORNAMENT_REVIEW_REQUIRED"
TIME_SIGNATURE_REFERENCE_OVERRIDE = "TIME_SIGNATURE_REFERENCE_OVERRIDE"
MP_MAX_MEDIAN_VELOCITY = 96
POSTPROCESS_VERSION = (
    f"music21-10.5.0/beat-grid/{ADAPTIVE_QUANTIZATION_VERSION}/pickup-v4/"
    f"{HarmonyConfig().version}/{VoicingConfig().version}/{VoiceCompressionConfig().version}/"
    f"{SIMPLE_ARPEGGIO_FILTER_VERSION}/{RESONANT_POLYPHONY_VERSION}/"
    f"{VOICE_REST_PRUNING_VERSION}/{DYNAMIC_MARKING_VERSION}/{SCORE_METADATA_VERSION}"
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
    tempo_bpm: int
    quality_flags: list[str]
    analysis: StructureAnalysis
    detected_analysis: StructureAnalysis | None
    notation: ResolvedNotationContext
    quantization: QuantizationDecision
    reconstruction: dict[str, object]


def build_score(
    events: list[NoteEvent],
    title: str = "SongDance Transcription",
    analysis: StructureAnalysis | None = None,
    sustain_evidence: SustainEvidence | None = None,
    harmonic_evidence: HarmonicEvidence | None = None,
    notation_context: NotationContext | None = None,
) -> ScoredTranscription:
    active_analysis = analysis or fallback_analysis(
        AnalysisConfig(), STRUCTURE_ANALYSIS_NOT_RUN, source="score_default"
    )
    detected_analysis = active_analysis
    active_notation = notation_context or NotationContext()
    if active_notation.time_signature is not None:
        active_analysis = dataclass_replace(
            active_analysis,
            time_signature=active_notation.time_signature,
            time_signature_source=active_notation.time_signature_source or "reference_score",
            time_signature_confidence=(
                active_notation.time_signature_confidence
                if active_notation.time_signature_confidence is not None
                else 1.0
            ),
        )
    flags = [*active_analysis.reason_codes, HAND_ASSIGNMENT_INFERRED]
    if active_notation.ornamentation_expected:
        flags.append(ORNAMENT_REVIEW_REQUIRED)
    if active_analysis.time_signature_source == "default":
        flags.append(TIME_SIGNATURE_ASSUMED)
    elif active_notation.time_signature is not None:
        flags.append(TIME_SIGNATURE_REFERENCE_OVERRIDE)
    quantization = select_quantization(
        events,
        active_analysis,
        forced_divisions_per_quarter=active_notation.quantization_divisions_per_quarter,
        source=active_notation.quantization_source,
    )
    quantized = quantize_events(events, active_analysis, quantization)
    pickup = decide_notation_pickup(
        quantized,
        active_analysis,
        measure_offset_units=active_notation.measure_offset_units,
        divisions_per_quarter=quantization.divisions_per_quarter,
    )
    notation = _resolve_notation_context(active_analysis, active_notation, pickup)
    notation_analysis = dataclass_replace(
        active_analysis,
        key_signature=notation.key_signature,
        key_signature_source=notation.key_signature_source,
        time_signature=notation.time_signature,
        time_signature_source=notation.time_signature_source,
        time_signature_confidence=notation.time_signature_confidence,
    )
    notation_input = (
        align_repeating_eighth_note_cycles(events, active_analysis, pickup)
        if pickup.candidate_pickup_units == quantization.divisions_per_quarter // 2
        else events
    )
    if notation_input is events:
        notation_input = quantized
    voicing = assign_hands(notation_input)
    arpeggio_filter = filter_simple_arpeggio_resonance(
        voicing.events,
        pedal_intervals=_notation_pedal_intervals(sustain_evidence),
        harmonic_evidence=harmonic_evidence,
    )
    notation_events = arpeggio_filter.events
    quarter_seconds = seconds_per_quarter(active_analysis)
    staff_distribution = staff_distribution_summary(
        notation_events,
        seconds_per_quarter=quarter_seconds,
        time_signature=active_analysis.time_signature,
    )
    reconstruction_version = POSTPROCESS_VERSION
    if FALSE_PICKUP_REJECTED_FULL_MEASURE in pickup.reason_codes:
        reconstruction_version = f"{POSTPROCESS_VERSION}/{EIGHTH_CYCLE_ALIGNMENT_VERSION}"
    if voicing.unknown_count:
        flags.append(UNKNOWN_HAND_NOTATION_FALLBACK)
    if staff_distribution["status"] == "suspect":
        flags.append(STAFF_DISTRIBUTION_SUSPECT)
    measure_offset_units = pickup.measure_offset_units
    if sustain_evidence is None or sustain_evidence.status != "available":
        flags.append(SUSTAIN_EVIDENCE_UNAVAILABLE)
    collapse_to_single_voice = voicing.strategy == "simple_arpeggio_stable_zone"
    with_mp = _should_mark_mp(notation_events, collapse_to_single_voice)

    try:
        score, structure, compression = _build_reconstructed_score(
            notation_events,
            title,
            notation_analysis,
            quarter_seconds,
            measure_offset_units,
            sustain_evidence,
            quantization.divisions_per_quarter,
            collapse_to_single_voice=collapse_to_single_voice,
            with_mp=with_mp,
        )
        reconstruction = {
            "status": "reconstructed",
            "version": reconstruction_version,
            "fallback_used": False,
            "error_code": None,
            "voicing": voicing.summary(),
            "staff_distribution": staff_distribution,
            "arpeggio_filter": arpeggio_filter.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
            "pickup": pickup.summary(),
            "notation": notation.summary(),
            "quantization": quantization.summary(),
            "voice_compression": compression,
        }
    except RECOVERABLE_SCORE_ERRORS as error:
        try:
            score, structure = _build_basic_score(
                notation_events,
                title,
                notation_analysis,
                quarter_seconds,
                measure_offset_units,
                quantization.divisions_per_quarter,
                with_mp=with_mp,
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
            "staff_distribution": staff_distribution,
            "arpeggio_filter": arpeggio_filter.summary(),
            "chord_count": structure["chord_count"],
            "voice_count": structure["voice_count"],
            "pickup": pickup.summary(),
            "notation": notation.summary(),
            "quantization": quantization.summary(),
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
        tempo_bpm=integer_tempo_bpm(active_analysis.bpm),
        quality_flags=flags,
        analysis=active_analysis,
        detected_analysis=detected_analysis,
        notation=notation,
        quantization=quantization,
        reconstruction=reconstruction,
    )


def _resolve_notation_context(
    analysis: StructureAnalysis,
    context: NotationContext,
    pickup: PickupDecision,
) -> ResolvedNotationContext:
    key_signature_confidence = (
        context.key_signature_confidence
        if context.key_signature_confidence is not None
        else analysis.key_confidence
    )
    if not 0 <= key_signature_confidence <= 1:
        raise ValueError("notation key signature confidence must be between 0 and 1")
    time_signature_confidence = (
        context.time_signature_confidence
        if context.time_signature_confidence is not None
        else analysis.time_signature_confidence
    )
    if not 0 <= time_signature_confidence <= 1:
        raise ValueError("notation time signature confidence must be between 0 and 1")
    return ResolvedNotationContext(
        local_tonal_center=analysis.key_signature,
        local_tonal_center_confidence=analysis.key_confidence,
        local_tonal_center_source=analysis.key_signature_source,
        key_signature=context.key_signature or analysis.key_signature,
        key_signature_source=context.key_signature_source
        or "inferred_local_tonal_center",
        key_signature_confidence=key_signature_confidence,
        time_signature=context.time_signature or analysis.time_signature,
        time_signature_source=context.time_signature_source or analysis.time_signature_source,
        time_signature_confidence=time_signature_confidence,
        measure_offset_units=pickup.measure_offset_units,
        measure_offset_source=context.measure_offset_source
        or "audio_downbeat_analysis",
        ornamentation_expected=context.ornamentation_expected,
        ornamentation_source=context.ornamentation_source,
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


def _should_mark_mp(events: list[NoteEvent], simple_arpeggio: bool) -> bool:
    return bool(events) and simple_arpeggio and median(event.velocity for event in events) <= 96
