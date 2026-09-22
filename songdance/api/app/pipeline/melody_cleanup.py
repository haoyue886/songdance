"""Conservative notation-only cleanup for explicitly declared treble melodies."""

from dataclasses import asdict, dataclass, replace
from math import isfinite

from app.pipeline.harmonics import HarmonicEvidence, NoteOnsetEvidence
from app.pipeline.transcribe import NoteEvent

VERSION = "melody-tail-evidence-v1"
ONSET_TOLERANCE = 0.08
MAX_DECAY_FIT_ERROR = 0.05


@dataclass(frozen=True)
class MelodyCleanup:
    events: list[NoteEvent]
    removals: list[dict[str, object]]
    duration_changes: list[dict[str, object]]
    status: str

    def summary(self) -> dict[str, object]:
        return {
            "version": VERSION,
            "status": self.status,
            "removals": self.removals,
            "duration_changes": self.duration_changes,
            "output_event_count": len(self.events),
            "thresholds": {
                "onset_seconds": ONSET_TOLERANCE,
                "max_decay_fit_error": MAX_DECAY_FIT_ERROR,
                "max_overhang_ratio": 0.5,
            },
        }


def clean_melody_tails(
    events: list[NoteEvent], evidence: HarmonicEvidence | None, *, enabled: bool
) -> MelodyCleanup:
    if not enabled or not events or any(e.pitch < 60 or e.hand == "left" for e in events):
        return MelodyCleanup(events, [], [], "not_applied")
    if evidence is None or evidence.status != "available":
        return MelodyCleanup(events, [], [], "evidence_unavailable")
    ordered = sorted(events, key=lambda e: (e.start_sec, e.pitch, e.end_sec))
    observations = [_observation(e, evidence) for e in ordered]
    removed: set[int] = set()
    removals = []
    for i, event in enumerate(ordered):
        observation = observations[i]
        if (
            observation is None
            or observation.independent_onset
            or observation.onset_growth > 1.0
            or observation.onset_energy > observation.pre_onset_energy
            or observation.decay_fit_error is None
            or not isfinite(observation.decay_fit_error)
            or observation.decay_fit_error > MAX_DECAY_FIT_ERROR
        ):
            continue
        previous = [j for j in range(i) if ordered[j].start_sec < event.start_sec - ONSET_TOLERANCE]
        if not previous:
            continue
        latest_start = max(ordered[j].start_sec for j in previous)
        parents = [
            j
            for j in previous
            if j not in removed
            and ordered[j].pitch == event.pitch
            and abs(ordered[j].start_sec - latest_start) <= ONSET_TOLERANCE
            and abs(ordered[j].end_sec - event.start_sec) <= ONSET_TOLERANCE
            and observations[j] is not None
            and observations[j].independent_onset
        ]
        attacks = [
            j
            for j, other in enumerate(ordered)
            if other.pitch != event.pitch
            and abs(other.start_sec - event.start_sec) <= ONSET_TOLERANCE
            and observations[j] is not None
            and observations[j].independent_onset
        ]
        if len(parents) != 1 or len(attacks) != 1:
            continue
        removed.add(i)
        removals.append(
            {
                "event": asdict(event),
                "reason": "DECAY_REDETECTED_AT_NEW_ATTACK",
                "previous_event": asdict(ordered[parents[0]]),
                "next_attack": asdict(ordered[attacks[0]]),
                "onset_evidence": asdict(observation),
            }
        )
    kept = [(e, observations[i]) for i, e in enumerate(ordered) if i not in removed]
    # Ambiguous polyphony prevents truncating any independent sustained voice.
    polyphonic = any(
        abs(a[0].start_sec - b[0].start_sec) <= ONSET_TOLERANCE
        for a, b in zip(kept, kept[1:], strict=False)
    )
    changed = []
    output = []
    for i, (event, _observation_value) in enumerate(kept):
        next_pair = kept[i + 1] if i + 1 < len(kept) else None
        if not polyphonic and next_pair and next_pair[1] and next_pair[1].independent_onset:
            boundary = next_pair[0].start_sec
            interval = boundary - event.start_sec
            # Only a short overhang is covered by the declared monophonic interpretation.
            if interval > ONSET_TOLERANCE and boundary < event.end_sec <= boundary + interval * 0.5:
                changed.append(
                    {
                        "event": asdict(event),
                        "end_sec": boundary,
                        "reason": "DECLARED_MELODY_NEXT_INDEPENDENT_ATTACK",
                        "next_onset_evidence": asdict(next_pair[1]),
                    }
                )
                event = replace(event, end_sec=boundary)
        output.append(event)
    return MelodyCleanup(output, removals, changed, "evaluated")


def _observation(event: NoteEvent, evidence: HarmonicEvidence) -> NoteOnsetEvidence | None:
    matches = [
        o
        for o in evidence.onset_observations
        if o.pitch == event.pitch
        and abs(o.start_sec - event.start_sec) < 1e-6
        and abs(o.end_sec - event.end_sec) < 1e-6
    ]
    if len(matches) != 1:
        return None
    value = matches[0]
    energies = (value.pre_onset_energy, value.onset_energy, value.onset_growth)
    if any(x is None or not isfinite(x) or x <= 0 for x in energies):
        return None
    return value
