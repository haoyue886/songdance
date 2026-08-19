from math import ceil, floor

from app.pipeline.transcribe import NoteEvent

STAFF_DISTRIBUTION_SUSPECT = "STAFF_DISTRIBUTION_SUSPECT"
BASS_MAX_PITCH = 59
TREBLE_MIN_PITCH = 64


def staff_distribution_summary(
    events: list[NoteEvent],
    *,
    seconds_per_quarter: float = 0.5,
    time_signature: str = "4/4",
) -> dict[str, object]:
    measure_seconds = _measure_quarters(time_signature) * seconds_per_quarter
    onsets: dict[float, list[int]] = {}
    measures: dict[int, dict[str, int]] = {}
    for event in events:
        onsets.setdefault(event.start_sec, []).append(event.pitch)
        measure = _measure(measures, floor(max(0.0, event.start_sec) / measure_seconds))
        measure["onset_count"] += 1
        if event.pitch <= BASS_MAX_PITCH:
            measure["bass_onset_count"] += 1
            if event.hand == "left":
                measure["left_bass_onset_count"] += 1
            last_measure = floor(max(event.start_sec, event.end_sec - 1e-6) / measure_seconds)
            for index in range(floor(event.start_sec / measure_seconds), last_measure + 1):
                active = _measure(measures, index)
                active["active_bass_count"] += 1
                if event.hand == "left":
                    active["left_active_bass_count"] += 1
        elif event.pitch >= TREBLE_MIN_PITCH:
            measure["treble_onset_count"] += 1
            if event.hand == "right":
                measure["right_treble_onset_count"] += 1

    wide_onset_count = sum(
        len(pitches) >= 2 and max(pitches) - min(pitches) >= 12
        for pitches in onsets.values()
    )
    left_count = sum(event.hand == "left" for event in events)
    right_count = sum(event.hand == "right" for event in events)
    unknown_count = len(events) - left_count - right_count
    known_count = left_count + right_count
    known_ratio = _ratio(known_count, len(events))
    minority_ratio = _ratio(min(left_count, right_count), known_count)
    bass_count = sum(event.pitch <= BASS_MAX_PITCH for event in events)
    left_bass_count = sum(
        event.pitch <= BASS_MAX_PITCH and event.hand == "left" for event in events
    )
    treble_count = sum(event.pitch >= TREBLE_MIN_PITCH for event in events)
    right_treble_count = sum(
        event.pitch >= TREBLE_MIN_PITCH and event.hand == "right" for event in events
    )
    bass_assignment_ratio = _ratio(left_bass_count, bass_count)
    treble_assignment_ratio = _ratio(right_treble_count, treble_count)
    bass_measures = [item for item in measures.values() if item["active_bass_count"]]
    covered_bass_measures = sum(item["left_active_bass_count"] > 0 for item in bass_measures)
    bass_measure_coverage_ratio = _ratio(covered_bass_measures, len(bass_measures))
    suspect_measure_count = sum(
        item["bass_onset_count"] >= 2
        and _ratio(item["left_bass_onset_count"], item["bass_onset_count"]) < 0.5
        for item in bass_measures
    )
    enough_texture = len(events) >= 32 and (
        wide_onset_count >= 4 or (bass_count >= 8 and treble_count >= 8)
    )
    per_measure_limit = max(2, ceil(len(bass_measures) * 0.3))
    suspect = enough_texture and (
        known_ratio < 0.7
        or minority_ratio < 0.15
        or (bass_count >= 8 and bass_assignment_ratio < 0.55)
        or (treble_count >= 8 and treble_assignment_ratio < 0.55)
        or (len(bass_measures) >= 2 and bass_measure_coverage_ratio < 0.6)
        or suspect_measure_count >= per_measure_limit
    )
    status = "suspect" if suspect else "passed" if enough_texture else "not_evaluated"
    return {
        "status": status,
        "reason_code": STAFF_DISTRIBUTION_SUSPECT if suspect else "",
        "left_count": left_count,
        "right_count": right_count,
        "unknown_count": unknown_count,
        "known_ratio": known_ratio,
        "minority_ratio": minority_ratio,
        "wide_onset_count": wide_onset_count,
        "bass_event_count": bass_count,
        "bass_assignment_ratio": bass_assignment_ratio,
        "treble_event_count": treble_count,
        "treble_assignment_ratio": treble_assignment_ratio,
        "bass_measure_count": len(bass_measures),
        "bass_measure_coverage_ratio": bass_measure_coverage_ratio,
        "suspect_measure_count": suspect_measure_count,
        "measures": [
            {"measure_index": index, **values} for index, values in sorted(measures.items())
        ],
    }


def _measure(measures: dict[int, dict[str, int]], index: int) -> dict[str, int]:
    return measures.setdefault(
        index,
        {
            "onset_count": 0,
            "bass_onset_count": 0,
            "left_bass_onset_count": 0,
            "active_bass_count": 0,
            "left_active_bass_count": 0,
            "treble_onset_count": 0,
            "right_treble_onset_count": 0,
        },
    )


def _measure_quarters(time_signature: str) -> float:
    numerator, denominator = map(int, time_signature.split("/", 1))
    return numerator * 4 / denominator


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0
