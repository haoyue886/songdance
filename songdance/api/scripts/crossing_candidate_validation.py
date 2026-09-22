"""Validate saved outputs, rather than trusting in-memory event counts."""

import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

import pretty_midi
from music21 import converter

from app.pipeline.score_io import read_musicxml_structure


def _key(start, pitch, duration):
    return round(float(start), 6), int(pitch), round(float(duration), 6)


def validate_saved_outputs(paths: dict[str, Path]) -> dict[str, object]:
    timeline = json.loads(paths["timeline"].read_text())
    midi = pretty_midi.PrettyMIDI(str(paths["midi"]))
    parsed = converter.parse(paths["musicxml"])
    tree = ElementTree.parse(paths["musicxml"])
    structure = read_musicxml_structure(paths["musicxml"])
    quarter = 60.0 / timeline["tempo_bpm"]
    expected = Counter(
        _key(e["start_sec"], e["pitch"], e["end_sec"] - e["start_sec"])
        for e in timeline["notation_notes"]
    )
    played = Counter(
        _key(n.start, n.pitch, n.end - n.start)
        for instrument in midi.instruments for n in instrument.notes
    )
    engraved = Counter(
        _key(float(n.getOffsetInHierarchy(part)) * quarter, p.midi,
             float(n.quarterLength) * quarter)
        for part in parsed.parts for n in part.recurse().notes for p in n.pitches
    )
    xml_sounds = [float(n.get("tempo")) for n in tree.findall(".//sound[@tempo]")]
    meters = {(t.findtext("beats"), t.findtext("beat-type"))
              for t in tree.findall(".//attributes/time")}
    checks = {
        "nonempty": bool(expected),
        "quarter_tempo_60": timeline["tempo_bpm"] == 60
        and set(midi.get_tempo_changes()[1]) == {60.0} and set(xml_sounds) == {60.0},
        "four_four": timeline["time_signature"] == "4/4" and meters == {("4", "4")}
        and [(t.numerator, t.denominator) for t in midi.time_signature_changes] == [(4, 4)],
        "two_staves_one_piano": structure["staff_count"] == 2
        and structure["musicxml_part_count"] == 1,
        "uniform_eighths": bool(expected) and all(k[2] == 0.5 for k in engraved)
        and all(k[2] == 0.5 for k in expected) and all(k[2] == 0.5 for k in played),
        "absolute_grid": all(abs(k[0] / 0.5 - round(k[0] / 0.5)) < 1e-6 for k in engraved),
        "xml_matches_timeline": engraved == expected,
        "midi_matches_timeline": played == expected,
        "no_structure_errors": not structure["errors"],
    }
    return {
        "status": "passed" if all(checks.values()) else "failed", "checks": checks,
        "xml_pitch_event_count": sum(engraved.values()),
        "midi_pitch_event_count": sum(played.values()),
        "onset_group_count": len({k[0] for k in engraved}),
        "last_notated_end_seconds": max((k[0] + k[2] for k in engraved), default=0),
        "xml_note_value_quarters": sorted({float(n.quarterLength) for n in parsed.recurse().notes}),
        "structure": structure,
    }
