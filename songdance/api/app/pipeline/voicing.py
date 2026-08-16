import hashlib
import json
from dataclasses import asdict, dataclass, replace
from statistics import median
from typing import Protocol

from app.pipeline.simple_arpeggio import apply_simple_arpeggio_strategy
from app.pipeline.transcribe import NoteEvent

VOICING_ALGORITHM_VERSION = "voicing-v2"
UNKNOWN_HAND_NOTATION_FALLBACK = "UNKNOWN_HAND_NOTATION_FALLBACK"


class TimedGroup(Protocol):
    start_units: int
    end_units: int


@dataclass(frozen=True)
class VoicingConfig:
    natural_left_pitch: int = 52
    natural_right_pitch: int = 68
    pitch_weight: float = 0.25
    continuity_weight: float = 0.75
    chord_role_bias: float = 0.12
    minimum_confidence: float = 0.16
    maximum_prediction_semitones: float = 12.0

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{VOICING_ALGORITHM_VERSION}/{digest}"


@dataclass(frozen=True)
class VoicingResult:
    events: list[NoteEvent]
    version: str
    left_count: int
    right_count: int
    unknown_count: int
    mean_confidence: float
    strategy: str
    reason_codes: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "left_count": self.left_count,
            "right_count": self.right_count,
            "unknown_count": self.unknown_count,
            "mean_confidence": self.mean_confidence,
            "strategy": self.strategy,
            "reason_codes": self.reason_codes,
        }


@dataclass
class _HandHistory:
    points: list[tuple[float, float]]

    def predict(self, at_time: float, natural_pitch: float, maximum_step: float) -> float:
        if not self.points:
            return natural_pitch
        latest_time, latest_pitch = self.points[-1]
        if len(self.points) == 1 or at_time <= latest_time:
            return latest_pitch
        previous_time, previous_pitch = self.points[-2]
        elapsed = latest_time - previous_time
        if elapsed <= 0:
            return latest_pitch
        projected = latest_pitch + (latest_pitch - previous_pitch) * (
            (at_time - latest_time) / elapsed
        )
        return latest_pitch + max(-maximum_step, min(maximum_step, projected - latest_pitch))

    def record(self, at_time: float, pitches: list[int]) -> None:
        if not pitches:
            return
        self.points.append((at_time, float(median(pitches))))
        self.points[:] = self.points[-2:]


def assign_hands(
    events: list[NoteEvent], config: VoicingConfig | None = None
) -> VoicingResult:
    active = config or VoicingConfig()
    histories = {"left": _HandHistory([]), "right": _HandHistory([])}
    assigned: list[NoteEvent] = []
    onsets: dict[float, list[NoteEvent]] = {}
    for event in events:
        onsets.setdefault(event.start_sec, []).append(event)

    for onset, onset_events in sorted(onsets.items()):
        ordered = sorted(onset_events, key=lambda item: (item.pitch, item.end_sec))
        low_pitch = ordered[0].pitch
        high_pitch = ordered[-1].pitch
        hand_pitches: dict[str, list[int]] = {"left": [], "right": []}
        for event in ordered:
            if event.hand in hand_pitches:
                hand = event.hand
                confidence = event.hand_confidence if event.hand_confidence is not None else 1.0
            else:
                left_cost = _assignment_cost(
                    event.pitch,
                    "left",
                    onset,
                    low_pitch,
                    high_pitch,
                    histories,
                    active,
                )
                right_cost = _assignment_cost(
                    event.pitch,
                    "right",
                    onset,
                    low_pitch,
                    high_pitch,
                    histories,
                    active,
                )
                confidence = _assignment_confidence(left_cost, right_cost)
                hand = None if confidence < active.minimum_confidence else (
                    "left" if left_cost < right_cost else "right"
                )
            assigned.append(
                replace(event, hand=hand, hand_confidence=round(confidence, 6))
            )
            if hand is not None:
                hand_pitches[hand].append(event.pitch)
        histories["left"].record(onset, hand_pitches["left"])
        histories["right"].record(onset, hand_pitches["right"])

    strategy = "continuity"
    reason_codes: tuple[str, ...] = ()
    assigned, strategy, reason_codes = apply_simple_arpeggio_strategy(assigned, events)
    ordered_events = sorted(
        assigned, key=lambda item: (item.start_sec, item.pitch, item.end_sec)
    )
    confidences = [event.hand_confidence or 0.0 for event in ordered_events]
    return VoicingResult(
        events=ordered_events,
        version=active.version,
        left_count=sum(event.hand == "left" for event in ordered_events),
        right_count=sum(event.hand == "right" for event in ordered_events),
        unknown_count=sum(event.hand is None for event in ordered_events),
        mean_confidence=round(sum(confidences) / len(confidences), 6)
        if confidences
        else 0.0,
        strategy=strategy,
        reason_codes=reason_codes,
    )


def notation_hand(event: NoteEvent) -> str:
    if event.hand in {"left", "right"}:
        return event.hand
    return "left" if event.pitch < 60 else "right"


def assign_voices(groups: list[TimedGroup]) -> list[list[TimedGroup]]:
    voices: list[list[TimedGroup]] = []
    voice_ends: list[int] = []
    for group in groups:
        available = next(
            (
                index
                for index, end_units in enumerate(voice_ends)
                if end_units <= group.start_units
            ),
            None,
        )
        if available is None:
            voices.append([group])
            voice_ends.append(group.end_units)
        else:
            voices[available].append(group)
            voice_ends[available] = group.end_units
    return voices


def _assignment_cost(
    pitch: int,
    hand: str,
    onset: float,
    low_pitch: int,
    high_pitch: int,
    histories: dict[str, _HandHistory],
    config: VoicingConfig,
) -> float:
    natural = (
        config.natural_left_pitch if hand == "left" else config.natural_right_pitch
    )
    prediction = histories[hand].predict(
        onset, natural, config.maximum_prediction_semitones
    )
    has_history = bool(histories[hand].points)
    pitch_weight = config.pitch_weight if has_history else 1.0
    continuity_weight = config.continuity_weight if has_history else 0.0
    cost = pitch_weight * abs(pitch - natural) / 24
    cost += continuity_weight * abs(pitch - prediction) / 12
    if hand == "left" and pitch == low_pitch:
        cost -= config.chord_role_bias
    if hand == "right" and pitch == high_pitch:
        cost -= config.chord_role_bias
    return max(0.0, cost)


def _assignment_confidence(left_cost: float, right_cost: float) -> float:
    return min(1.0, abs(left_cost - right_cost) / (left_cost + right_cost + 0.25))
