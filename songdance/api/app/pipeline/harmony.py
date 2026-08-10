import hashlib
import json
from dataclasses import asdict, dataclass

from app.pipeline.quantize import GRID_DIVISIONS
from app.pipeline.transcribe import NoteEvent

HARMONY_ALGORITHM_VERSION = "harmony-v1"


@dataclass(frozen=True)
class HarmonyConfig:
    onset_tolerance_units: int = 0
    duration_tolerance_units: int = 1
    maximum_chord_size: int = 4

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{HARMONY_ALGORITHM_VERSION}/{digest}"


@dataclass(frozen=True)
class NotationGroup:
    start_units: int
    end_units: int
    pitches: tuple[int, ...]
    velocity: int
    confidence: float


def group_harmony(
    events: list[NoteEvent],
    seconds_per_quarter: float,
    measure_offset_units: int,
    config: HarmonyConfig | None = None,
) -> list[NotationGroup]:
    active = config or HarmonyConfig()
    groups: list[list[tuple[int, int, NoteEvent]]] = []
    for event in sorted(events, key=lambda item: (item.start_sec, item.end_sec, item.pitch)):
        start_units, end_units = _event_units(
            event, seconds_per_quarter, measure_offset_units
        )
        target = next(
            (
                group
                for group in groups
                if len(group) < active.maximum_chord_size
                and abs(group[0][0] - start_units) <= active.onset_tolerance_units
                and abs(group[0][1] - end_units) <= active.duration_tolerance_units
                and all(item[2].pitch != event.pitch for item in group)
            ),
            None,
        )
        if target is None:
            groups.append([(start_units, end_units, event)])
        else:
            target.append((start_units, end_units, event))

    notation_groups = []
    for group in groups:
        events_in_group = [item[2] for item in group]
        notation_groups.append(
            NotationGroup(
                start_units=min(item[0] for item in group),
                end_units=max(item[1] for item in group),
                pitches=tuple(sorted(event.pitch for event in events_in_group)),
                velocity=round(
                    sum(event.velocity for event in events_in_group) / len(events_in_group)
                ),
                confidence=round(
                    sum(event.confidence for event in events_in_group) / len(events_in_group),
                    6,
                ),
            )
        )
    return sorted(
        notation_groups,
        key=lambda item: (
            item.start_units,
            -(item.end_units - item.start_units),
            item.pitches,
        ),
    )


def _event_units(
    event: NoteEvent, seconds_per_quarter: float, measure_offset_units: int
) -> tuple[int, int]:
    start_units = (
        round(event.start_sec / seconds_per_quarter * GRID_DIVISIONS)
        + measure_offset_units
    )
    end_units = max(
        start_units + 1,
        round(event.end_sec / seconds_per_quarter * GRID_DIVISIONS)
        + measure_offset_units,
    )
    return start_units, end_units
