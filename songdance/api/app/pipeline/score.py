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
from app.pipeline.analysis import (
    AnalysisConfig,
    StructureAnalysis,
    enrich_analysis_with_tonality,
    fallback_analysis,
)
from app.pipeline.arpeggio_resonance import (
    SIMPLE_ARPEGGIO_FILTER_VERSION,
    filter_simple_arpeggio_resonance,
)
from app.pipeline.crossing_eighth import crossing_notation_grid, select_crossing_eighth_events
from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.errors import ScoreGenerationError
from app.pipeline.harmonics import HarmonicEvidence
from app.pipeline.harmony import HarmonyConfig
from app.pipeline.melody_cleanup import clean_melody_tails
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
    active_analysis = enrich_analysis_with_tonality(active_analysis, events)
    detected_analysis = active_analysis
    active_notation = notation_context or NotationContext()
    if active_notation.tempo_bpm is not None:
        active_analysis = dataclass_replace(
            active_analysis,
            bpm=float(active_notation.tempo_bpm),
            bpm_confidence=active_notation.time_signature_confidence or 1.0,
        )
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
    if active_notation.texture_hint == "crossing_eighth_melody":
        active_analysis = crossing_notation_grid(active_analysis)
    if active_notation.ornamentation_expected:
        flags.append(ORNAMENT_REVIEW_REQUIRED)
    if active_analysis.time_signature_source == "default":
        flags.append(TIME_SIGNATURE_ASSUMED)
    elif active_notation.time_signature is not None:
        flags.append(TIME_SIGNATURE_REFERENCE_OVERRIDE)
    melody_cleanup = clean_melody_tails(
        events,
        harmonic_evidence,
        enabled=active_notation.texture_hint
        in {
            "monophonic_melody",
            "eighth_note_melody",
            "six_note_melody",
        },
    )
    crossing_tail_cleanup = {"status": "not_applied"}
    notation_source = melody_cleanup.events
    if active_notation.texture_hint == "crossing_eighth_melody":
        notation_source, crossing_tail_cleanup = clean_crossing_tails(
            notation_source, harmonic_evidence, 60.0 / active_analysis.bpm
        )
    quantization = select_quantization(
        notation_source,
        active_analysis,
        forced_divisions_per_quarter=active_notation.quantization_divisions_per_quarter,
        source=active_notation.quantization_source,
    )
    quantized = quantize_events(
        notation_source,
        active_analysis,
        quantization,
        cap_melody_durations=active_notation.texture_hint is None,
    )
    compound_cleanup = {"status": "not_applied"}
    if active_notation.texture_hint == "compound_68":
        quantized, compound_cleanup = _apply_compound_68_constraints(
            quantized, seconds_per_quarter(active_analysis), active_analysis.time_signature
        )
        quantized, slot_cleanup = _select_compound_68_slots(
            quantized, seconds_per_quarter(active_analysis)
        )
        compound_cleanup["slot_selection"] = slot_cleanup
    six_note_cleanup = {"status": "not_applied"}
    if active_notation.texture_hint == "six_note_melody":
        quantized, six_note_cleanup = _select_eighth_note_slots(
            quantized,
            seconds_per_quarter(active_analysis),
            harmonic_evidence=harmonic_evidence,
        )
        quantized = _cap_eighth_note_durations(quantized, seconds_per_quarter(active_analysis))
    crossing_cleanup = {"status": "not_applied"}
    if active_notation.texture_hint == "crossing_eighth_melody":
        quantized, crossing_cleanup = select_crossing_eighth_events(
            notation_source, seconds_per_quarter(active_analysis), harmonic_evidence
        )
        if crossing_cleanup["status"] == "needs_review":
            flags.append("CROSSING_EVENTS_REVIEW_REQUIRED")
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
        align_repeating_eighth_note_cycles(notation_source, active_analysis, pickup)
        if pickup.candidate_pickup_units == quantization.divisions_per_quarter // 2
        else notation_source
    )
    if notation_input is notation_source:
        notation_input = quantized
    slot_selection = {"status": "not_applied", "selected_count": len(notation_input)}
    if active_notation.texture_hint == "eighth_note_melody":
        notation_input, slot_selection = _select_eighth_note_slots(
            notation_input, seconds_per_quarter(active_analysis)
        )
        notation_input = _cap_eighth_note_durations(
            notation_input, seconds_per_quarter(active_analysis)
        )
        slot_selection["duration_rule"] = "cap_to_next_eighth_attack"
    fixture_melody = active_notation.texture_hint in {
        "monophonic_melody",
        "eighth_note_melody",
        "six_note_melody",
    }
    single_staff = (
        fixture_melody
        and bool(notation_input)
        and all(event.pitch >= 60 and event.hand != "left" for event in notation_input)
        and len({event.start_sec for event in notation_input}) == len(notation_input)
        and all(
            left.end_sec <= right.start_sec + 1e-6
            for left, right in zip(notation_input, notation_input[1:], strict=False)
        )
    )
    if single_staff:
        notation_input = [
            dataclass_replace(event, hand="right", hand_confidence=1.0) for event in notation_input
        ]
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
    if single_staff:
        reconstruction_version += "/explicit-staff-layout-v1"
    if active_notation.texture_hint == "crossing_eighth_melody":
        reconstruction_version += "/" + str(crossing_cleanup["version"])
        reconstruction_version += "/" + str(crossing_tail_cleanup["version"])
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
            single_staff=single_staff,
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
                single_staff=single_staff,
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
    reconstruction["staff_layout"] = {
        "value": "single_treble" if single_staff else "grand_staff",
        "source": "fixture_texture_hint" if single_staff else "default",
        "version": "explicit-staff-layout-v1",
    }
    reconstruction["melody_cleanup"] = melody_cleanup.summary()
    reconstruction["eighth_slot_selection"] = slot_selection
    reconstruction["compound_68_cleanup"] = compound_cleanup
    reconstruction["six_note_melody_cleanup"] = six_note_cleanup
    reconstruction["crossing_eighth_cleanup"] = crossing_cleanup
    reconstruction["crossing_tail_cleanup"] = crossing_tail_cleanup
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


def _select_eighth_note_slots(
    events: list[NoteEvent],
    quarter_seconds: float,
    *,
    harmonic_evidence: HarmonicEvidence | None = None,
) -> tuple[list[NoteEvent], dict[str, object]]:
    if not events or quarter_seconds <= 0:
        return events, {"status": "no_events", "selected_count": len(events)}
    slot_seconds = quarter_seconds / 2
    origin = min(event.start_sec for event in events)
    by_slot: dict[int, list[NoteEvent]] = {}
    for event in events:
        slot = round((event.start_sec - origin) / slot_seconds)
        if abs(event.start_sec - (origin + slot * slot_seconds)) <= slot_seconds * 0.42:
            by_slot.setdefault(slot, []).append(event)
    selected = []
    harmonic_rejected_count = 0
    non_independent_rejected_count = 0
    ambiguous_slot_count = 0
    removals = []
    for slot, candidates in sorted(by_slot.items()):
        eligible = []
        for event in candidates:
            reason = _harmonic_rejection_reason(event, harmonic_evidence)
            if reason is None:
                eligible.append(event)
                continue
            harmonic_rejected_count += 1
            removals.append(_slot_removal(slot, event, reason))
        independent = [
            event
            for event in eligible
            if _independent_onset_status(event, harmonic_evidence) is True
        ]
        if independent:
            retained = []
            for event in eligible:
                if _independent_onset_status(event, harmonic_evidence) is False:
                    non_independent_rejected_count += 1
                    removals.append(
                        _slot_removal(slot, event, "NON_INDEPENDENT_ONSET_AUDIO_EVIDENCE")
                    )
                else:
                    retained.append(event)
            eligible = retained
        if len(eligible) > 1:
            ambiguous_slot_count += 1
        selected.extend(eligible)
    status = "ambiguous" if ambiguous_slot_count else "applied"
    return selected, {
        "status": status,
        "slot_seconds": round(slot_seconds, 6),
        "origin_seconds": round(origin, 6),
        "input_count": len(events),
        "selected_count": len(selected),
        "dropped_count": len(events) - len(selected),
        "harmonic_rejected_count": harmonic_rejected_count,
        "non_independent_rejected_count": non_independent_rejected_count,
        "ambiguous_slot_count": ambiguous_slot_count,
        "removals": removals,
    }


def _harmonic_rejection_reason(event: NoteEvent, evidence: HarmonicEvidence | None) -> str | None:
    if evidence is None or evidence.status != "available":
        return None
    if any(
        removal.harmonic_pitch == event.pitch
        and abs(removal.harmonic_start_sec - event.start_sec) <= 0.08
        and not removal.independent_onset
        for removal in evidence.removals
    ):
        return "HARMONIC_REMOVAL_AUDIO_EVIDENCE"
    if any(
        observation.harmonic_pitch == event.pitch
        and abs(observation.harmonic_start_sec - event.start_sec) <= 0.08
        and not observation.independent_onset
        for observation in evidence.observations
    ):
        return "HARMONIC_OBSERVATION_AUDIO_EVIDENCE"
    return None


def _independent_onset_status(event: NoteEvent, evidence: HarmonicEvidence | None) -> bool | None:
    if evidence is None or evidence.status != "available":
        return None
    matches = [item for item in evidence.onset_observations if item.matches(event)]
    return matches[0].independent_onset if len(matches) == 1 else None


def _slot_removal(slot: int, event: NoteEvent, reason: str) -> dict[str, object]:
    return {
        "slot": slot,
        "pitch": event.pitch,
        "start_sec": round(event.start_sec, 6),
        "end_sec": round(event.end_sec, 6),
        "reason": reason,
    }


def _apply_compound_68_constraints(
    events: list[NoteEvent], quarter_seconds: float, time_signature: str
) -> tuple[list[NoteEvent], dict[str, object]]:
    """Apply teacher-reviewed 6/8 cleanup for the compound-68 fixture only."""
    if time_signature != "6/8" or not events or quarter_seconds <= 0:
        return events, {"status": "skipped", "reason": "not_6_8_or_empty"}
    low_frequency = [event for event in events if event.pitch < 48]
    # 保守保留低音：没有逐事件音频证据时不能把合法低音当噪音删除。
    kept = list(events)
    measure_seconds = quarter_seconds * 3
    accented = []
    for event in sorted(kept, key=lambda item: (item.start_sec, item.pitch)):
        measure_index = int(event.start_sec // measure_seconds)
        measure_start = measure_index * measure_seconds
        if abs(event.start_sec - measure_start) <= quarter_seconds * 0.25 and event.pitch >= 60:
            accented.append(
                dataclass_replace(
                    event,
                    end_sec=max(event.end_sec, event.start_sec + quarter_seconds * 0.75),
                )
            )
        else:
            accented.append(event)
    return accented, {
        "status": "applied",
        "removed_suspicious_low_frequency_count": 0,
        "removed_suspicious_low_frequency_pitches": [],
        "preserved_low_frequency_count": len(low_frequency),
        "audit_reason": "INSUFFICIENT_EVENT_LEVEL_EVIDENCE_PRESERVE",
        "first_note_duration_rule": "dotted_eighth",
        "accented_first_note_count": sum(
            1
            for event in accented
            if abs(event.start_sec % measure_seconds) <= quarter_seconds * 0.25
            and event.pitch >= 60
        ),
    }


def _select_compound_68_slots(
    events: list[NoteEvent], quarter_seconds: float
) -> tuple[list[NoteEvent], dict[str, object]]:
    """Keep one treble attack per eighth-note slot for the reviewed fixture."""
    if not events or quarter_seconds <= 0:
        return events, {"status": "skipped", "selected_count": len(events)}
    slot_seconds = quarter_seconds / 2
    origin = min(event.start_sec for event in events)
    by_slot: dict[int, list[NoteEvent]] = {}
    for event in events:
        slot = round((event.start_sec - origin) / slot_seconds)
        if abs(event.start_sec - (origin + slot * slot_seconds)) <= slot_seconds * 0.4:
            by_slot.setdefault(slot, []).append(event)
    selected = [
        max(candidates, key=lambda event: (event.confidence, event.velocity, -event.pitch))
        for slot, candidates in sorted(by_slot.items())
    ]
    return selected, {
        "status": "applied",
        "slot_seconds": round(slot_seconds, 6),
        "input_count": len(events),
        "selected_count": len(selected),
        "dropped_count": len(events) - len(selected),
    }


def _cap_eighth_note_durations(events: list[NoteEvent], quarter_seconds: float) -> list[NoteEvent]:
    slot_seconds = quarter_seconds / 2
    ordered = sorted(events, key=lambda event: event.start_sec)
    starts = sorted({event.start_sec for event in ordered})
    next_starts = dict(zip(starts, starts[1:], strict=False))
    return [
        dataclass_replace(
            event,
            end_sec=min(
                event.end_sec,
                next_starts.get(event.start_sec, event.start_sec + slot_seconds),
            ),
        )
        for event in ordered
    ]


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
        key_signature_source=context.key_signature_source or "inferred_local_tonal_center",
        key_signature_confidence=key_signature_confidence,
        time_signature=context.time_signature or analysis.time_signature,
        time_signature_source=context.time_signature_source or analysis.time_signature_source,
        time_signature_confidence=time_signature_confidence,
        measure_offset_units=pickup.measure_offset_units,
        measure_offset_source=context.measure_offset_source or "audio_downbeat_analysis",
        ornamentation_expected=context.ornamentation_expected,
        ornamentation_source=context.ornamentation_source,
        tempo_bpm=context.tempo_bpm or integer_tempo_bpm(analysis.bpm),
        tempo_source=context.tempo_source or "analysis_bpm",
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
