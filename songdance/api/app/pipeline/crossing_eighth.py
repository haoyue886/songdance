"""Notation-only timing for the explicitly reviewed crossing exercise."""

from dataclasses import asdict, replace
from math import ceil, floor, isfinite

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.harmonics import HarmonicEvidence, NoteOnsetEvidence
from app.pipeline.transcribe import NoteEvent

VERSION = "crossing-eighth-v2"
REVIEW_SHIFT_RATIO = 0.4


def crossing_notation_grid(analysis: StructureAnalysis) -> StructureAnalysis:
    """Keep the detected grid on the caller's saved analysis; expose the notation grid here."""
    quarter = 60.0 / analysis.bpm
    beats = range(ceil(analysis.duration_seconds / quarter) + 1)
    return replace(
        analysis,
        beat_grid_seconds=tuple(round(i * quarter, 6) for i in beats),
        downbeat_grid_seconds=tuple(round(i * quarter, 6) for i in beats if i % 4 == 0),
        downbeat_phase_index=0,
    )


def select_crossing_eighth_events(
    events: list[NoteEvent],
    quarter_seconds: float,
    evidence: HarmonicEvidence | None = None,
) -> tuple[list[NoteEvent], dict[str, object]]:
    if not isfinite(quarter_seconds) or quarter_seconds <= 0:
        raise ValueError("crossing quarter duration must be positive and finite")
    slot_seconds = quarter_seconds / 2
    selected: list[NoteEvent] = []
    removals: list[dict[str, object]] = []
    retained: list[dict[str, object]] = []
    changes: list[dict[str, object]] = []
    large_shifts: list[int] = []
    suspect_ids: list[int] = []
    for index, event in enumerate(events):
        # Match BEFORE quantizing: nearby reattacks must never inherit an old removal.
        observation = _onset_observation(event, evidence)
        removal = next(
            (r for r in evidence.removals if r.matches(event) and not r.independent_onset),
            None,
        ) if evidence is not None and evidence.status == "available" else None
        if removal is not None and not (observation and observation.independent_onset):
            removals.append({
                "input_index": index, "event": asdict(event),
                "reason": "CONFIRMED_HARMONIC_REMOVAL", "evidence": removal.summary(),
            })
            continue
        if (observation is not None and not observation.independent_onset) or (
            evidence is not None and evidence.status == "available"
            and any(r.matches(event) for r in evidence.observations)
        ):
            suspect_ids.append(index)
        slot = max(0, floor(event.start_sec / slot_seconds + 0.5))
        start = round(slot * slot_seconds, 6)
        end = round((slot + 1) * slot_seconds, 6)
        shift = abs(start - event.start_sec)
        if shift > slot_seconds * REVIEW_SHIFT_RATIO:
            large_shifts.append(index)
        updated = replace(event, start_sec=start, end_sec=end)
        selected.append(updated)
        retained.append({"input_index": index, "event": asdict(event), "slot": slot})
        if updated != event:
            changes.append({
                "input_index": index, "slot": slot, "pitch": event.pitch,
                "from_start_sec": event.start_sec, "from_end_sec": event.end_sec,
                "to_start_sec": start, "to_end_sec": end,
                "reason": "EXPERT_UNIFORM_EIGHTH_GRID",
            })
    selected.sort(key=lambda e: (e.start_sec, e.pitch, e.end_sec))
    return selected, {
        "version": VERSION,
        "status": "no_events" if not events else (
            "needs_review" if suspect_ids or large_shifts else "applied"
        ),
        "slot_seconds": slot_seconds,
        "origin_seconds": 0.0,
        "input_count": len(events),
        "selected_count": len(selected),
        "dropped_count": len(removals),
        "harmonic_rejected_count": len(removals),
        "unconfirmed_event_indices": suspect_ids,
        "large_shift_event_indices": large_shifts,
        "max_start_shift_seconds": max(
            (abs(c["to_start_sec"] - c["from_start_sec"]) for c in changes), default=0.0
        ),
        "duration_rule": "uniform_eighth_note",
        "duration_change_count": len(changes),
        "removals": removals,
        "retained": retained,
        "duration_changes": changes,
    }


def _onset_observation(
    event: NoteEvent, evidence: HarmonicEvidence | None
) -> NoteOnsetEvidence | None:
    if evidence is None or evidence.status != "available":
        return None
    matches = [
        o for o in evidence.onset_observations
        if o.pitch == event.pitch and o.start_sec == event.start_sec and o.end_sec == event.end_sec
    ]
    return matches[0] if len(matches) == 1 else None
