from collections import Counter

from music21 import clef, converter, meter, stream, tempo

from app.pipeline.score_notation import populate_part
from app.pipeline.transcribe import NoteEvent


def test_same_onset_different_endings_survive_xml_ties(tmp_path):
    # One grid-unit difference must not extend the short tone into the long tone.
    events = [
        NoteEvent(0, 1.75, 60, 80, 0.8, hand="right"),
        NoteEvent(0, 2, 64, 80, 0.8, hand="right"),
        NoteEvent(2, 3, 67, 80, 0.8, hand="right"),
    ]
    part = stream.Part()
    part.insert(0, clef.TrebleClef())
    part.insert(0, meter.TimeSignature("2/4"))
    part.insert(0, tempo.MetronomeMark(number=60))
    populate_part(part, events, "right", 1, 0, None, 4)
    score = stream.Score()
    score.insert(0, part)
    path = tmp_path / "score.musicxml"
    score.write("musicxml", fp=str(path))
    parsed = converter.parse(path).stripTies(inPlace=False)
    actual = Counter(
        (int(p.midi), float(n.getOffsetInHierarchy(staff)), float(n.quarterLength))
        for staff in parsed.parts
        for n in staff.recurse().notes
        for p in n.pitches
    )
    assert actual == Counter((e.pitch, e.start_sec, e.end_sec - e.start_sec) for e in events)
