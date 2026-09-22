"""Conservative tail re-detection removal for an explicitly reviewed crossing exercise."""

from dataclasses import asdict
from math import isfinite

from app.pipeline.harmonics import HarmonicEvidence, NoteOnsetEvidence
from app.pipeline.transcribe import NoteEvent

VERSION = "crossing-tail-evidence-v2"
TOLERANCE = 0.08
MAX_DECAY_ERROR = 0.05
MAX_TRANSIENT_ERROR = 0.01
MAX_ROOT_SLOTS = 2


def clean_crossing_tails(
    events: list[NoteEvent], evidence: HarmonicEvidence | None, quarter_seconds: float
) -> tuple[list[NoteEvent], dict[str, object]]:
    if not isfinite(quarter_seconds) or quarter_seconds <= 0:
        raise ValueError("crossing quarter duration must be positive and finite")
    summary: dict[str, object] = {
        "version": VERSION,
        "status": "no_events" if not events else "evidence_unavailable",
        "input_count": len(events),
        "output_count": len(events),
        "removed_count": 0,
        "removals": [],
        "thresholds": {
            "onset_seconds": TOLERANCE,
            "max_decay_fit_error": MAX_DECAY_ERROR,
            "max_transient_fit_error": MAX_TRANSIENT_ERROR,
            "max_root_slots": MAX_ROOT_SLOTS,
            "slot_seconds": quarter_seconds / 2,
        },
    }
    if not events or evidence is None or evidence.status != "available":
        return events, summary
    # Never let duplicate/conflicting measurements silently overwrite one another.
    observations = [_observation(e, evidence) for e in events]
    order = sorted(range(len(events)), key=lambda i: (events[i].start_sec, events[i].pitch))
    roots: dict[int, int] = {}
    chain_depth: dict[int, int] = {}
    removed: set[int] = set()
    removals: list[dict[str, object]] = []
    for index in order:
        event, observation = events[index], observations[index]
        if not _is_uninterrupted_decay(observation):
            continue
        # A same-key unison or nearby re-strike has ambiguous ownership. Preserve it.
        if any(
            i != index
            and e.pitch == event.pitch
            and abs(e.start_sec - event.start_sec) <= TOLERANCE
            for i, e in enumerate(events)
        ):
            continue
        earlier = [
            i
            for i in order
            if events[i].pitch == event.pitch and events[i].start_sec < event.start_sec - TOLERANCE
        ]
        if not earlier:
            continue
        latest = max(events[i].start_sec for i in earlier)
        parents = [i for i in earlier if latest - events[i].start_sec <= TOLERANCE]
        if len(parents) != 1:
            continue
        parent = parents[0]
        if abs(events[parent].end_sec - event.start_sec) > TOLERANCE:
            continue
        root = roots.get(parent, parent)
        if not _is_attack(observations[root]):
            continue
        if parent != root and parent not in removed:
            continue
        if (
            event.start_sec - events[root].start_sec
            > quarter_seconds / 2 * MAX_ROOT_SLOTS + TOLERANCE
        ):
            continue
        attacks = [
            i
            for i, other in enumerate(events)
            if other.pitch != event.pitch
            and abs(other.start_sec - event.start_sec) <= TOLERANCE
            and _is_attack(observations[i])
        ]
        if not attacks:
            continue
        removed.add(index)
        roots[index] = root
        chain_depth[index] = chain_depth.get(parent, 0) + 1
        removals.append(
            {
                "input_index": index,
                "event": asdict(event),
                "reason": "DECAY_REDETECTED_AT_INDEPENDENT_ATTACK",
                "root_input_index": root,
                "root_event": asdict(events[root]),
                "root_onset_evidence": asdict(observations[root]),
                "predecessor_input_index": parent,
                "direct_predecessor": asdict(events[parent]),
                "predecessor_onset_evidence": asdict(observations[parent]),
                "chain_depth": chain_depth[index],
                "other_independent_attacks": [
                    {
                        "input_index": i,
                        "event": asdict(events[i]),
                        "onset_evidence": asdict(observations[i]),
                    }
                    for i in attacks
                ],
                "onset_evidence": asdict(observation),
            }
        )
    kept = [event for i, event in enumerate(events) if i not in removed]
    summary.update(
        status="evaluated", output_count=len(kept), removed_count=len(removals), removals=removals
    )
    return kept, summary


def _observation(event: NoteEvent, evidence: HarmonicEvidence) -> NoteOnsetEvidence | None:
    matches = [
        o
        for o in evidence.onset_observations
        if o.pitch == event.pitch and o.start_sec == event.start_sec and o.end_sec == event.end_sec
    ]
    return matches[0] if len(matches) == 1 else None


def _is_attack(observation: NoteOnsetEvidence | None) -> bool:
    return bool(
        observation is not None
        and observation.independent_onset
        and isfinite(observation.onset_growth)
        and observation.onset_growth >= 2
    )


def _is_uninterrupted_decay(observation: NoteOnsetEvidence | None) -> bool:
    if observation is None or observation.independent_onset:
        return False
    values = (observation.onset_growth, observation.pre_onset_energy, observation.onset_energy)
    if any(v is None or not isfinite(v) or v <= 0 for v in values):
        return False
    error = observation.decay_fit_error
    transient = observation.transient_fit_error
    return bool(
        error is not None
        and isfinite(error)
        and 0 <= error <= MAX_DECAY_ERROR
        and transient is not None
        and isfinite(transient)
        and 0 <= transient <= MAX_TRANSIENT_ERROR
        and observation.onset_growth <= 1
        and observation.onset_energy <= observation.pre_onset_energy
    )
