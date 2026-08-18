from dataclasses import replace

from app.pipeline.harmony import NotationGroup


def merge_same_pitch_overlaps(
    groups: list[NotationGroup], onset_units: tuple[int, ...], tolerance: int
) -> tuple[list[NotationGroup], int]:
    merged: list[NotationGroup] = []
    latest_by_pitch: dict[int, int] = {}
    merge_count = 0
    for group in groups:
        if len(group.pitches) != 1:
            merged.append(group)
            continue
        pitch = group.pitches[0]
        previous_index = latest_by_pitch.get(pitch)
        has_retrigger = any(
            abs(group.start_units - onset) <= tolerance for onset in onset_units
        )
        if previous_index is not None:
            previous = merged[previous_index]
            if group.start_units < previous.end_units and not has_retrigger:
                merged[previous_index] = replace(
                    previous,
                    end_units=max(previous.end_units, group.end_units),
                    velocity=max(previous.velocity, group.velocity),
                    confidence=max(previous.confidence, group.confidence),
                )
                merge_count += 1
                continue
        latest_by_pitch[pitch] = len(merged)
        merged.append(group)
    return merged, merge_count
