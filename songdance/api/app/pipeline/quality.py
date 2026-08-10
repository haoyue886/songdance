import hashlib
import importlib.metadata
import json
from collections import Counter
from dataclasses import asdict

import numpy as np
from mir_eval.transcription import match_notes, precision_recall_f1_overlap

from app.pipeline.analysis import AnalysisConfig
from app.pipeline.cleanup import CleanupConfig
from app.pipeline.score import POSTPROCESS_VERSION, ScoredTranscription
from app.pipeline.score_validation import score_structure_summary
from app.pipeline.transcribe import NoteEvent

QUALITY_REPORT_VERSION = "quality-report-v6"


def pipeline_postprocess_version(
    cleanup_summary: dict[str, object] | None = None,
    analysis_summary: dict[str, object] | None = None,
) -> str:
    cleanup_version = (
        cleanup_summary.get("version") if cleanup_summary is not None else None
    ) or CleanupConfig().version
    analysis_version = (
        analysis_summary.get("version") if analysis_summary is not None else None
    ) or AnalysisConfig().version
    return f"{cleanup_version}/{analysis_version}/{POSTPROCESS_VERSION}"
QUALITY_RATING_VALUES = {"direct_use", "minor_edits", "needs_redo"}


def build_quality_report(
    raw_events: list[NoteEvent],
    scored: ScoredTranscription | None,
    *,
    reference_events: list[NoteEvent] | None = None,
    human_rating: str | None = None,
    model_version: str | None = None,
    thresholds: dict[str, float] | None = None,
    musicxml_status: str = "passed",
    musicxml_error_code: str | None = None,
    structure_summary: dict[str, object] | None = None,
    cleaned_events: list[NoteEvent] | None = None,
    cleanup_summary: dict[str, object] | None = None,
    analysis_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    raw = _sorted_events(raw_events)
    cleaned_source = (
        cleaned_events if cleaned_events is not None else scored.notes if scored else None
    )
    cleaned = _sorted_events(cleaned_source or [])
    confidences = [event.confidence for event in raw]
    default_structure = (
        score_structure_summary(scored.score)
        if scored is not None
        else {"status": "not_evaluated", "errors": []}
    )
    structure = dict(structure_summary or default_structure)
    structure_errors = list(structure.get("errors", []))
    if musicxml_status != "passed":
        structure_errors.append(musicxml_error_code or "MUSICXML_UNAVAILABLE")
    structure["errors"] = sorted(set(structure_errors))
    musicxml_parse = {"status": musicxml_status}
    if musicxml_error_code is not None:
        musicxml_parse["error_code"] = musicxml_error_code
    active_analysis = analysis_summary or (
        scored.analysis.summary() if scored is not None else _not_applied_analysis()
    )
    return {
        "schema_version": 4,
        "quality_report_version": QUALITY_REPORT_VERSION,
        "postprocess_version": pipeline_postprocess_version(
            cleanup_summary, active_analysis
        ),
        "raw_note_count": len(raw),
        "cleaned_note_count": len(cleaned) if cleaned_source is not None else None,
        "cleanup": cleanup_summary or _not_applied_cleanup(len(raw)),
        "analysis": active_analysis,
        "reconstruction": scored.reconstruction
        if scored is not None
        else {
            "status": "not_evaluated",
            "fallback_used": False,
            "error_code": None,
        },
        "confidence": {
            "min": round(min(confidences), 6) if confidences else None,
            "max": round(max(confidences), 6) if confidences else None,
            "mean": round(sum(confidences) / len(confidences), 6) if confidences else None,
        },
        "model": {
            "version": model_version or "not_recorded",
            "thresholds": dict(sorted((thresholds or {}).items())),
        },
        "dependencies": dependency_versions(),
        "note_metrics": evaluate_note_events(raw, reference_events),
        "human_rating": _human_rating(human_rating),
        "duplicate_event_count": _duplicate_count(raw),
        "overlap_count": _overlap_count(cleaned) if cleaned_source is not None else None,
        "raw_event_fingerprint": _fingerprint(raw),
        "cleaned_event_fingerprint": _fingerprint(cleaned) if cleaned_source is not None else None,
        "musicxml_parse": musicxml_parse,
        "structure": structure,
        "structure_errors": structure["errors"],
    }


def _not_applied_cleanup(source_note_count: int) -> dict[str, object]:
    return {
        "status": "not_applied",
        "version": CleanupConfig().version,
        "source_note_count": source_note_count,
        "output_note_count": source_note_count,
        "reason_counts": {},
        "fallback_used": False,
        "error_code": None,
    }


def _not_applied_analysis() -> dict[str, object]:
    return {
        "status": "not_applied",
        "version": AnalysisConfig().version,
        "source": "not_applied",
        "reason_codes": ["STRUCTURE_ANALYSIS_NOT_RUN"],
    }


def evaluate_note_events(
    estimated: list[NoteEvent], reference: list[NoteEvent] | None
) -> dict[str, object]:
    if reference is None:
        return {
            "status": "not_evaluated",
            "reason": "REFERENCE_TRUTH_UNAVAILABLE",
            "precision": None,
            "recall": None,
            "f1": None,
            "matched_note_count": None,
            "mean_onset_error_ms": None,
            "mean_pitch_error_semitones": None,
        }

    reference_intervals, reference_pitches = _arrays(reference)
    estimated_intervals, estimated_pitches = _arrays(estimated)
    matches = match_notes(
        reference_intervals,
        reference_pitches,
        estimated_intervals,
        estimated_pitches,
        onset_tolerance=0.1,
        offset_ratio=None,
    )
    precision, recall, f1, overlap = precision_recall_f1_overlap(
        reference_intervals,
        reference_pitches,
        estimated_intervals,
        estimated_pitches,
        onset_tolerance=0.1,
        offset_ratio=None,
    )
    onset_errors = [
        abs(reference[reference_index].start_sec - estimated[estimated_index].start_sec)
        for reference_index, estimated_index in matches
    ]
    pitch_errors = [
        abs(reference[reference_index].pitch - estimated[estimated_index].pitch)
        for reference_index, estimated_index in matches
    ]
    return {
        "status": "evaluated",
        "reference_note_count": len(reference),
        "estimated_note_count": len(estimated),
        "matched_note_count": len(matches),
        "precision": _round_metric(precision),
        "recall": _round_metric(recall),
        "f1": _round_metric(f1),
        "overlap": _round_metric(overlap),
        "mean_onset_error_ms": _round_metric(1_000 * np.mean(onset_errors))
        if onset_errors
        else None,
        "mean_pitch_error_semitones": _round_metric(np.mean(pitch_errors))
        if pitch_errors
        else None,
    }


def dependency_versions() -> dict[str, str]:
    return {
        package: _distribution_version(package)
        for package in ("basic-pitch", "librosa", "mir-eval", "music21", "pretty_midi")
    }


def _distribution_version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


def _arrays(events: list[NoteEvent]) -> tuple[np.ndarray, np.ndarray]:
    intervals = np.asarray(
        [(event.start_sec, event.end_sec) for event in events], dtype=float
    ).reshape((-1, 2))
    pitches = np.asarray(
        [440.0 * 2 ** ((event.pitch - 69) / 12) for event in events], dtype=float
    )
    return intervals, pitches


def _human_rating(rating: str | None) -> dict[str, object]:
    if rating is None:
        return {"status": "not_evaluated", "rating": None}
    if rating not in QUALITY_RATING_VALUES:
        raise ValueError("human rating must be a supported three-level rating")
    return {"status": "evaluated", "rating": rating}


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def _sorted_events(events: list[NoteEvent]) -> list[NoteEvent]:
    return sorted(
        events,
        key=_event_sort_key,
    )


def _event_sort_key(
    event: NoteEvent,
) -> tuple[float, float, int, int, float, str, float]:
    return (
        event.start_sec,
        event.end_sec,
        event.pitch,
        event.velocity,
        event.confidence,
        event.hand or "",
        event.hand_confidence if event.hand_confidence is not None else -1.0,
    )


def _duplicate_count(events: list[NoteEvent]) -> int:
    keys = [(event.start_sec, event.end_sec, event.pitch) for event in events]
    return sum(count - 1 for count in Counter(keys).values() if count > 1)


def _overlap_count(events: list[NoteEvent]) -> int:
    overlaps = 0
    last_end_by_hand: dict[str, float] = {}
    for event in events:
        hand = event.hand or "unknown"
        if event.start_sec < last_end_by_hand.get(hand, 0):
            overlaps += 1
        last_end_by_hand[hand] = max(last_end_by_hand.get(hand, 0), event.end_sec)
    return overlaps


def _fingerprint(events: list[NoteEvent]) -> str:
    payload = [asdict(event) for event in events]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
