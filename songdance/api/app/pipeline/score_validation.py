from fractions import Fraction

from music21 import chord, key, meter, note, stream

MIN_REST_QUARTER_LENGTH = Fraction(1, 4)


def score_structure_summary(
    score: stream.Score, *, validate_measure_durations: bool = False
) -> dict[str, object]:
    errors: list[str] = []
    if len(score.parts) != 2:
        errors.append("EXPECTED_TWO_PIANO_PARTS")
    if not list(score.recurse().notes):
        errors.append("EMPTY_SCORE")

    notation_chords = list(score.recurse().getElementsByClass(chord.Chord))
    notation_rests = list(score.recurse().getElementsByClass(note.Rest))
    notation_voices = list(score.recurse().getElementsByClass(stream.Voice))
    measures = list(score.recurse().getElementsByClass(stream.Measure))
    for notation_chord in notation_chords:
        pitches = [value.midi for value in notation_chord.pitches]
        if len(pitches) != len(set(pitches)):
            errors.append("DUPLICATE_CHORD_PITCH")
        if notation_chord.duration.quarterLength <= 0:
            errors.append("NON_POSITIVE_DURATION")

    for scored_note in score.recurse().getElementsByClass(note.Note):
        if scored_note.duration.quarterLength <= 0:
            errors.append("NON_POSITIVE_DURATION")

    for notation_voice in notation_voices:
        previous_end = Fraction(0)
        for element in sorted(notation_voice.notesAndRests, key=lambda item: item.offset):
            offset = Fraction(element.offset)
            if offset < previous_end and not isinstance(element, note.Rest):
                errors.append("OVERLAPPING_VOICE_EVENTS")
                break
            previous_end = max(
                previous_end,
                offset + Fraction(element.duration.quarterLength),
            )

    measure_duration_error_count, partial_final_measure_count = _measure_errors(score)
    if validate_measure_durations and measure_duration_error_count:
        errors.append("MEASURE_DURATION_MISMATCH")

    short_rest_count = sum(
        Fraction(rest.duration.quarterLength) < MIN_REST_QUARTER_LENGTH
        for rest in notation_rests
    )
    if short_rest_count:
        errors.append("SUB_GRID_REST_FRAGMENT")

    time_signatures = sorted(
        {value.ratioString for value in score.recurse().getElementsByClass(meter.TimeSignature)}
    )
    if len(time_signatures) != 1:
        errors.append("INCONSISTENT_TIME_SIGNATURE")
    key_signatures = sorted(
        {value.sharps for value in score.recurse().getElementsByClass(key.KeySignature)}
    )
    if len(key_signatures) > 1:
        errors.append("INCONSISTENT_KEY_SIGNATURE")

    return {
        "part_count": len(score.parts),
        "measure_count": len(measures),
        "chord_count": len(notation_chords),
        "voice_count": len(notation_voices),
        "rest_count": len(notation_rests),
        "short_rest_count": short_rest_count,
        "measure_duration_error_count": measure_duration_error_count,
        "partial_final_measure_count": partial_final_measure_count,
        "time_signatures": time_signatures,
        "key_signatures": key_signatures,
        "key_signature_status": "detected" if key_signatures else "not_analyzed",
        "errors": sorted(set(errors)),
    }


def score_structure_errors(
    score: stream.Score, *, validate_measure_durations: bool = False
) -> list[str]:
    return list(
        score_structure_summary(
            score, validate_measure_durations=validate_measure_durations
        )["errors"]
    )


def raise_for_structure_errors(
    score: stream.Score, *, validate_measure_durations: bool = False
) -> None:
    errors = score_structure_errors(
        score, validate_measure_durations=validate_measure_durations
    )
    if errors:
        raise ValueError(", ".join(errors))


def _measure_errors(score: stream.Score) -> tuple[int, int]:
    error_count = 0
    partial_final_count = 0
    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        for index, measure in enumerate(measures):
            try:
                bar_duration = Fraction(measure.barDuration.quarterLength)
            except Exception:
                continue
            actual_duration = Fraction(measure.duration.quarterLength) + Fraction(
                measure.paddingLeft
            )
            is_final = index == len(measures) - 1
            if actual_duration > bar_duration or (not is_final and actual_duration != bar_duration):
                error_count += 1
            elif is_final and actual_duration < bar_duration:
                partial_final_count += 1
    first_measures = [
        measures[0]
        for part in score.parts
        if (measures := list(part.getElementsByClass(stream.Measure)))
    ]
    if any(Fraction(measure.paddingLeft) > 0 for measure in first_measures):
        boundaries = {
            (Fraction(measure.paddingLeft), Fraction(measure.duration.quarterLength))
            for measure in first_measures
        }
        if len(boundaries) > 1:
            error_count += 1
    return error_count, partial_final_count
