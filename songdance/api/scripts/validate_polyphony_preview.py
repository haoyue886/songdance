"""Gate score semantics after tie reconstruction; structure parsing alone is insufficient."""

from collections import Counter

from music21 import converter

from scripts.compare_piano_model_outputs import read_midi


def key(pitch, start, duration):
    return int(pitch), round(float(start), 6), round(float(duration), 6)


def validate(xml, midi, notes, quarter_seconds):
    parsed = converter.parse(xml).stripTies(inPlace=False)
    engraved = Counter(
        key(
            pitch.midi,
            n.getOffsetInHierarchy(part) * quarter_seconds,
            n.quarterLength * quarter_seconds,
        )
        for part in parsed.parts
        for n in part.recurse().notes
        for pitch in n.pitches
    )
    expected = Counter(key(n.pitch, n.start_sec, n.end_sec - n.start_sec) for n in notes)
    played = Counter(
        key(n["pitch"], n["start_sec"], n["end_sec"] - n["start_sec"]) for n in read_midi(midi)
    )
    # 60 BPM and quarter-subdivision grid are exactly representable by this candidate.
    checks = {"xml_matches_events": engraved == expected, "midi_matches_events": played == expected}
    return {
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "expected_events": sum(expected.values()),
        "xml_tied_events": sum(engraved.values()),
        "midi_events": sum(played.values()),
        "xml_only": list((engraved - expected).elements()),
        "missing_or_changed_xml": list((expected - engraved).elements()),
        "reader": "music21 stripTies; disagreement blocks export acceptance",
    }
