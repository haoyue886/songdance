from dataclasses import replace
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from music21 import converter, note

from app.pipeline.analysis import AnalysisConfig, fallback_analysis
from app.pipeline.score import NotationContext, build_score, read_musicxml_structure, write_musicxml
from app.pipeline.score_io import read_musicxml_piano_layout
from app.pipeline.transcribe import NoteEvent


def melody():
    return [
        NoteEvent(i, i + 1, [60, 62, 64, 67, 69, 67, 64, 62][i % 8], 90, 0.9) for i in range(16)
    ]


def make_score(events=None):
    return build_score(
        melody() if events is None else events,
        analysis=replace(fallback_analysis(AnalysisConfig(), "test"), bpm=60),
        notation_context=NotationContext(texture_hint="monophonic_melody"),
    )


def test_single_staff_round_trip_keeps_every_note_and_timing(tmp_path):
    scored = make_score()
    assert scored.reconstruction["fallback_used"] is False
    assert len(scored.score.parts) == 1
    assert scored.reconstruction["staff_layout"]["source"] == "fixture_texture_hint"
    destination = tmp_path / "single.musicxml"
    write_musicxml(scored, destination)
    summary = read_musicxml_structure(destination)
    assert summary["staff_count"] == 1
    assert summary["musicxml_part_count"] == 1
    assert summary["clefs"] == {"1": "G2"}
    assert summary["rest_count"] == 0
    assert summary["errors"] == []
    parsed = converter.parse(destination)
    notes = list(parsed.recurse().getElementsByClass(note.Note))
    assert [
        (n.pitch.midi, float(n.getOffsetInHierarchy(parsed)), float(n.quarterLength)) for n in notes
    ] == [(n.pitch, n.start_sec, n.end_sec - n.start_sec) for n in melody()]


def test_single_staff_loads_in_external_parsers(tmp_path):
    from scripts.score_parser_validation import validate_external_parsers

    destination = tmp_path / "single.musicxml"
    write_musicxml(make_score(), destination)
    parsers = validate_external_parsers([destination])[str(destination.resolve())]
    assert parsers["xmllint"]["status"] == "passed"
    assert parsers["osmd"]["status"] == "passed"


@pytest.mark.parametrize("pitch,end,hand", [(36, 8, None), (55, 1, None), (64, 1, "left")])
def test_hint_cannot_remove_bass_or_explicit_left_hand(tmp_path, pitch, end, hand):
    events = [*melody(), NoteEvent(0, end, pitch, 30, 0.3, hand=hand)]
    scored = make_score(events)
    assert len(scored.score.parts) == 2
    assert len(scored.notation_notes) == len(events)
    assert any(n.pitch == pitch and n.hand == "left" for n in scored.notation_notes)
    destination = tmp_path / "grand.musicxml"
    write_musicxml(scored, destination)
    assert read_musicxml_structure(destination)["staff_count"] == 2


def test_single_staff_fallback_does_not_restore_empty_bass(tmp_path, monkeypatch):
    import app.pipeline.score as module

    def fail(*args, **kwargs):
        raise ValueError("forced reconstructed path failure")

    monkeypatch.setattr(module, "_build_reconstructed_score", fail)
    scored = make_score()
    assert scored.reconstruction["fallback_used"] is True
    destination = tmp_path / "fallback.musicxml"
    write_musicxml(scored, destination)
    assert read_musicxml_structure(destination)["staff_count"] == 1


def test_direct_fallback_rejects_left_hand_instead_of_dropping_it():
    from app.pipeline.score_construction import build_basic_score

    with pytest.raises(ValueError, match="SINGLE_STAFF_REQUIRES_TREBLE_EVENTS"):
        build_basic_score(
            [NoteEvent(0, 1, 48, 90, .9, hand="left")], "test",
            fallback_analysis(AnalysisConfig(), "test"), .5, 0, 4,
            single_staff=True,
        )


@pytest.mark.parametrize(
    "mutation", ["extra_part", "bass_clef", "staff_two", "later_staves", "instrument"]
)
def test_single_staff_xml_rejects_invalid_structure(tmp_path, mutation):
    destination = tmp_path / "invalid.musicxml"
    write_musicxml(make_score(), destination)
    tree = ET.parse(destination)
    root = tree.getroot()
    if mutation == "extra_part":
        ET.SubElement(root, "part", id="second")
    elif mutation == "bass_clef":
        root.find("./part/measure/attributes/clef/sign").text = "F"
    elif mutation == "staff_two":
        ET.SubElement(root.find("./part/measure/note"), "staff").text = "2"
    elif mutation == "later_staves":
        attributes = ET.SubElement(root.findall("./part/measure")[1], "attributes")
        ET.SubElement(attributes, "staves").text = "2"
    else:
        root.find("./part-list/score-part/part-name").text = "Violin"
    tree.write(destination)
    with pytest.raises(ValueError):
        read_musicxml_piano_layout(destination)


def test_09_current_events_export_as_single_staff_without_unexpected_fallback(tmp_path):
    import json

    source = (
        Path(__file__).parent
        / "fixtures/audio/structure-review-artifacts/09-light-noise/timeline.json"
    )
    data = json.loads(source.read_text())
    events = [
        NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], n["confidence"])
        for n in data["notation_notes"]
    ]
    scored = make_score(events)
    assert scored.reconstruction["fallback_used"] is False
    assert len(scored.notation_notes) == len(events)
    destination = tmp_path / "09.musicxml"
    write_musicxml(scored, destination)
    assert read_musicxml_structure(destination)["staff_count"] == 1
