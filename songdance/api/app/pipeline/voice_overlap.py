from dataclasses import replace

from app.pipeline.harmony import NotationGroup

_MAXIMUM_CHORD_SIZE = 4


def merge_same_pitch_overlaps(
    groups: list[NotationGroup], onset_units: tuple[int, ...], tolerance: int
) -> tuple[list[NotationGroup], int]:
    merged: list[NotationGroup] = []
    latest_by_pitch: dict[int, int] = {}
    merge_count = 0
    for group in groups:
        for pitch in group.pitches:
            pitch_group = replace(group, pitches=(pitch,))
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
            merged.append(pitch_group)
    return _recompose_chords(merged), merge_count


def _recompose_chords(groups: list[NotationGroup]) -> list[NotationGroup]:
    by_metadata: dict[tuple[int, int, int, float], list[list[int]]] = {}
    for group in groups:
        key = (
            group.start_units,
            group.end_units,
            group.velocity,
            group.confidence,
        )
        chord = next(
            (
                pitches
                for pitches in by_metadata.setdefault(key, [])
                if len(pitches) < _MAXIMUM_CHORD_SIZE and group.pitches[0] not in pitches
            ),
            None,
        )
        if chord is None:
            by_metadata[key].append([group.pitches[0]])
        else:
            chord.append(group.pitches[0])

    recomposed = [
        NotationGroup(start, end, tuple(sorted(pitches)), velocity, confidence)
        for (start, end, velocity, confidence), chords in by_metadata.items()
        for pitches in chords
    ]
    return sorted(
        recomposed,
        key=lambda group: (
            group.start_units,
            -(group.end_units - group.start_units),
            group.pitches,
        ),
    )
