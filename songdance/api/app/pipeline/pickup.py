from fractions import Fraction

from music21 import note, stream

from app.pipeline.quantize import GRID_DIVISIONS


def apply_pickup_measures(score: stream.Score, measure_offset_units: int) -> None:
    if measure_offset_units <= 0:
        return
    padding = Fraction(measure_offset_units, GRID_DIVISIONS)
    for part in score.parts:
        measures = list(part.getElementsByClass(stream.Measure))
        if not measures:
            continue
        first = measures[0]
        if list(first.recurse().notes):
            containers = list(first.getElementsByClass(stream.Voice)) or [first]
            for container in containers:
                _trim_pickup_padding(container, padding)
        else:
            for rest in list(first.recurse().getElementsByClass(note.Rest)):
                first.remove(rest, recurse=True)
            first.insert(0, note.Rest(quarterLength=first.barDuration.quarterLength - padding))
        first.paddingLeft = padding


def _trim_pickup_padding(container: stream.Stream, padding: Fraction) -> None:
    for element in list(container.notesAndRests):
        start = Fraction(element.offset)
        end = start + Fraction(element.quarterLength)
        if end <= padding:
            container.remove(element)
        elif start < padding:
            container.setElementOffset(element, 0)
            element.quarterLength = end - padding
        else:
            container.setElementOffset(element, start - padding)
