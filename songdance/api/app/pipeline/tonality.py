"""Deterministic, auditable local-tonality evidence from note events."""

import hashlib
import json
from dataclasses import asdict, dataclass
from statistics import median

from app.pipeline.transcribe import NoteEvent

TONALITY_ALGORITHM_VERSION = "local-tonality-evidence-v1"
TONICIZATION = "TONICIZATION_ONLY"
LEADING_TONE_ABSENT = "leading_tone_absent"
UNSUPPORTED_MODE = "UNSUPPORTED_MODE"


@dataclass(frozen=True)
class TonalityConfig:
    minimum_cadence_score: float = 0.72
    minimum_notation_score: float = 0.8
    minimum_candidate_gap: float = 0.12
    leading_tone_ratio: float = 0.015

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return f"{TONALITY_ALGORITHM_VERSION}/{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


@dataclass(frozen=True)
class TonalityEvidence:
    version: str
    candidates: tuple[dict[str, object], ...]
    selected: str | None
    notation_eligible: bool
    reason_codes: tuple[str, ...]
    evidence: dict[str, object]

    def summary(self) -> dict[str, object]:
        return asdict(self)


def analyze_local_tonality(
    events: list[NoteEvent],
    key_candidates: tuple[dict[str, object], ...] | list[dict[str, object]],
    *,
    config: TonalityConfig | None = None,
) -> TonalityEvidence:
    active = config or TonalityConfig()
    ordered = sorted(events, key=lambda event: (event.start_sec, event.pitch, event.end_sec))
    if not ordered:
        return TonalityEvidence(
            active.version, (), None, False, ("NO_TONAL_EVENTS",), _empty_evidence()
        )
    pitch_classes = [event.pitch % 12 for event in ordered]
    counts = {pitch: pitch_classes.count(pitch) for pitch in range(12)}
    terminal = ordered[-1].pitch % 12
    cadence = _cadence_evidence(ordered, terminal)
    candidates = []
    for item in key_candidates:
        value = str(item.get("value", ""))
        if not value or " " not in value:
            continue
        tonic_name, mode = value.split(" ", 1)
        if mode not in {"major", "minor"}:
            continue
        tonic = _PITCH_NAMES.index(tonic_name) if tonic_name in _PITCH_NAMES else None
        if tonic is None:
            continue
        leading = (tonic - 1) % 12
        leading_ratio = counts[leading] / len(pitch_classes)
        tonic_ratio = counts[tonic] / len(pitch_classes)
        cadence_score = float(cadence["scores"].get(tonic, 0.0))
        score = max(0.0, min(1.0, 0.45 * cadence_score + 0.3 * tonic_ratio + 0.25 * leading_ratio))
        if mode == "minor":
            score = max(0.0, score - 0.08 if leading_ratio == 0 else score)
        candidates.append(
            {
                "value": value,
                "score": round(score, 6),
                "pitch_class_count": counts[tonic],
                "leading_tone_count": counts[leading],
                "leading_tone_ratio": round(leading_ratio, 6),
                "cadence_score": round(cadence_score, 6),
            }
        )
    score_total = sum(float(item["score"]) for item in candidates) or 1.0
    for item in candidates:
        item["score"] = round(float(item["score"]) / score_total, 6)
    candidates.sort(key=lambda item: (-float(item["score"]), str(item["value"])))
    top_candidates = candidates[:2]
    top_total = sum(float(item["score"]) for item in top_candidates)
    if top_candidates and top_total > 0:
        for item in top_candidates:
            item["score"] = round(float(item["score"]) / top_total, 6)
    elif top_candidates:
        share = round(1.0 / len(top_candidates), 6)
        for item in top_candidates:
            item["score"] = share
    top = tuple(top_candidates)
    top_score = float(top[0]["score"]) if top else 0.0
    second_score = float(top[1]["score"]) if len(top) > 1 else 0.0
    gap = top_score - second_score
    cadence_supported = bool(
        cadence["terminal_cadence"]
        and float(cadence["selected_score"]) >= active.minimum_cadence_score
    )
    selected = str(top[0]["value"]) if top else None
    eligible = bool(
        top
        and cadence_supported
        and top_score >= active.minimum_notation_score
        and gap >= active.minimum_candidate_gap
    )
    reasons = []
    if not cadence_supported:
        reasons.append(TONICIZATION)
    if (
        top
        and float(top[0]["leading_tone_ratio"]) < active.leading_tone_ratio
        and not selected.startswith(("C major", "A minor"))
    ):
        reasons.append(LEADING_TONE_ABSENT)
        eligible = False
    if not eligible:
        selected = None
    if not candidates and key_candidates:
        reasons.append(UNSUPPORTED_MODE)
    pitch_groups = _onset_groups(ordered)
    note_groups = _onset_pitch_groups(ordered)
    harmonic_groups = [group for group in pitch_groups if len(group) >= 3]
    chord_roots = [root for group in harmonic_groups for root in _triad_roots(group)]
    structural_returns = (
        [int(cadence["selected_tonic"])] if cadence["terminal_cadence"] else []
    )
    return TonalityEvidence(
        version=active.version,
        candidates=top,
        selected=selected,
        notation_eligible=eligible,
        reason_codes=tuple(reasons),
        evidence={
            "terminal_pitch_class": terminal,
            "pitch_class_counts": counts,
            "cadence": cadence,
            "candidate_gap": round(gap, 6),
            "harmonic_evidence": {
                "source": "quantized_note_events",
                "chord_roots": chord_roots,
                "chord_triads": [list(group) for group in harmonic_groups],
                "bass_pitch_classes": [min(group) % 12 for group in note_groups],
                "structural_tonic_returns": structural_returns,
                "counter_evidence": list(reasons),
            },
        },
    )


def _cadence_evidence(events: list[NoteEvent], terminal: int) -> dict[str, object]:
    groups = _onset_groups(events)
    scores = {tonic: 0.0 for tonic in range(12)}
    terminal_cadence = False
    if len(groups) >= 2:
        for index, (previous_values, final_values) in enumerate(
            zip(groups, groups[1:], strict=False)
        ):
            previous = set(previous_values)
            final = set(final_values)
            for tonic in range(12):
                dominant = {(tonic + 7) % 12, (tonic + 11) % 12, (tonic + 2) % 12}
                target = {tonic, (tonic + 4) % 12, (tonic + 7) % 12}
                if dominant <= previous and target <= final:
                    scores[tonic] = max(scores[tonic], 1.0)
                    terminal_cadence = terminal_cadence or index == len(groups) - 2
        if scores[terminal] == 0:
            scores[terminal] = 0.35
    selected_tonic = max(scores, key=scores.__getitem__)
    return {
        "type": "authentic_cadence" if scores[selected_tonic] >= 1.0 else "none_or_inconclusive",
        "selected_tonic": selected_tonic,
        "selected_score": scores[selected_tonic],
        "terminal_cadence": terminal_cadence,
        "scores": scores,
        "onset_group_count": len(groups),
    }


def _onset_groups(events: list[NoteEvent]) -> list[tuple[int, ...]]:
    starts = sorted({event.start_sec for event in events})
    if not starts:
        return []
    interval = median(
        right - left for left, right in zip(starts, starts[1:], strict=False) if right > left
    ) if len(starts) > 1 else 0.0
    tolerance = max(0.02, interval * 0.08)
    groups: list[list[NoteEvent]] = []
    for event in events:
        if groups and abs(event.start_sec - groups[-1][0].start_sec) <= tolerance:
            groups[-1].append(event)
        else:
            groups.append([event])
    return [tuple(sorted({event.pitch % 12 for event in group})) for group in groups]


def _onset_pitch_groups(events: list[NoteEvent]) -> list[tuple[int, ...]]:
    starts = sorted({event.start_sec for event in events})
    if not starts:
        return []
    interval = (
        median(right - left for left, right in zip(starts, starts[1:], strict=False))
        if len(starts) > 1
        else 0.0
    )
    tolerance = max(0.02, interval * 0.08)
    groups: list[list[NoteEvent]] = []
    for event in events:
        if groups and abs(event.start_sec - groups[-1][0].start_sec) <= tolerance:
            groups[-1].append(event)
        else:
            groups.append([event])
    return [tuple(sorted(event.pitch for event in group)) for group in groups]


def _triad_roots(group: tuple[int, ...]) -> tuple[int, ...]:
    values = set(group)
    roots = []
    for root in values:
        if {(root + interval) % 12 for interval in (0, 4, 7)} <= values:
            roots.append(root)
        elif {(root + interval) % 12 for interval in (0, 3, 7)} <= values:
            roots.append(root)
    return tuple(sorted(set(roots)))


def _empty_evidence() -> dict[str, object]:
    return {
        "terminal_pitch_class": None,
        "pitch_class_counts": {},
        "cadence": {"type": "none"},
        "harmonic_evidence": {
            "source": "quantized_note_events",
            "chord_roots": [],
            "chord_triads": [],
            "bass_pitch_classes": [],
            "structural_tonic_returns": [],
            "counter_evidence": ["NO_TONAL_EVENTS"],
        },
    }


_PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
