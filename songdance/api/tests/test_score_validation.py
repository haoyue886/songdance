import json
from copy import deepcopy
from pathlib import Path
from xml.etree import ElementTree

import pretty_midi
import pytest
from music21 import dynamics, expressions, layout, note, stream, tempo

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.quantize import integer_tempo_bpm
from app.pipeline.score import (
    SCORE_RECONSTRUCTION_FALLBACK,
    build_score,
    write_musicxml,
    write_quantized_midi,
)
from app.pipeline.score_io import read_musicxml_piano_layout, read_musicxml_structure
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.score_parser_validation import validate_external_parsers


@pytest.mark.parametrize(("bpm", "expected"), [(117.49, 117), (117.5, 118), (118.5, 119)])
def test_integer_tempo_uses_half_up_rounding(bpm: float, expected: int) -> None:
    assert integer_tempo_bpm(bpm) == expected


def test_reconstructed_score_has_chords_and_no_voice_overlap() -> None:
    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0, 1, 64, 90, 0.9),
            NoteEvent(0, 1, 67, 90, 0.9),
            NoteEvent(0.5, 1.5, 72, 90, 0.9),
        ]
    )

    assert scored.reconstruction["status"] == "reconstructed"
    assert scored.reconstruction["chord_count"] >= 1
    assert scored.reconstruction["voice_count"] >= 2
    assert score_structure_errors(scored.score) == []


def test_repeated_arpeggio_is_one_piano_part_with_two_staves(tmp_path) -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    artifact_root = fixture_root / "structure-review-artifacts/04-arpeggios"
    timeline = json.loads((artifact_root / "timeline.json").read_text(encoding="utf-8"))
    events = [
        NoteEvent(**{key: value for key, value in item.items() if key != "id"})
        for item in timeline["notes"]
    ]
    evidence = extract_sustain_evidence(
        fixture_root / "generated/04-arpeggios.wav",
        pretty_midi.PrettyMIDI(str(fixture_root / "generated/04-arpeggios.mid")),
    )

    scored = build_score(
        events,
        analysis=StructureAnalysis(**timeline["analysis"]),
        sustain_evidence=evidence,
    )
    destination = tmp_path / "arpeggio.musicxml"
    write_musicxml(scored, destination)
    midi_destination = tmp_path / "arpeggio.mid"
    write_quantized_midi(scored, midi_destination)
    timeline_destination = tmp_path / "arpeggio-timeline.json"
    write_timeline(
        scored,
        timeline_destination,
        cleanup_summary=timeline["cleanup"],
    )
    written_timeline = json.loads(timeline_destination.read_text(encoding="utf-8"))
    written_midi = pretty_midi.PrettyMIDI(str(midi_destination))
    xml = destination.read_text(encoding="utf-8")

    assert "<alter>0</alter>" not in xml
    assert read_musicxml_piano_layout(destination) == {
        "musicxml_score_part_count": 1,
        "musicxml_part_count": 1,
        "staff_count": 2,
        "measure_count": 15,
        "clefs": {"1": "G2", "2": "F4"},
        "staff_numbers": ["1", "2"],
        "voices_by_staff": {"1": ["1"], "2": ["2"]},
        "backup_count": 15,
        "pedal_mark_count": 1,
    }
    structure = read_musicxml_structure(destination)
    assert structure["part_count"] == 1
    assert structure["measure_count"] == 15
    assert structure["music21_staff_count"] == 2
    assert structure["staff_measure_count"] == 30
    assert xml.count("<score-part id=") == 1
    assert xml.count("<part id=") == 1
    assert xml.count("<staves>2</staves>") == 1
    assert xml.count("<metronome ") == 1
    assert xml.count("<sound tempo=") == 1
    assert "<per-minute>117</per-minute>" in xml
    assert '<sound tempo="117"' in xml
    assert xml.count("<mp />") == 1
    assert xml.count("<pedal ") == 2
    assert len(list(scored.score.recurse().getElementsByClass(stream.Voice))) == 0
    assert len(list(scored.score.recurse().getElementsByClass(expressions.PedalMark))) == 1
    assert scored.reconstruction["voice_compression"]["single_voice_applied"] is True
    assert scored.reconstruction["arpeggio_filter"] == {
        "version": "simple-arpeggio-filter-v3",
        "applied": True,
        "removed_event_count": 97,
        "stable_cycle_count": 14,
        "matched_slot_count": 119,
        "reason_codes": ("SIMPLE_ARPEGGIO_RESONANCE_FILTERED",),
    }
    assert len(written_timeline["notes"]) == timeline["cleanup"]["output_note_count"] == 216
    assert len(written_timeline["notation_notes"]) == 119
    assert sum(len(instrument.notes) for instrument in written_midi.instruments) == 216
    assert len(written_midi.instruments) == 2
    assert {instrument.name for instrument in written_midi.instruments} == {"Piano"}
    assert len(written_midi.get_tempo_changes()[0]) == 1
    assert [round(value) for value in written_midi.get_tempo_changes()[1]] == [117]
    assert scored.tempo_bpm == 117
    assert timeline["analysis"]["bpm"] == 117.453835
    assert written_timeline["tempo_bpm"] == 117
    assert [
        mark.number
        for mark in scored.score.recurse().getElementsByClass(tempo.MetronomeMark)
    ] == [117]
    assert [mark.value for mark in scored.score.recurse().getElementsByClass(dynamics.Dynamic)] == [
        "mp"
    ]

    left_expected = [
        (0.0, 48),
        (0.5, 55),
    ]
    right_expected = [
        (1.0, 60),
        (1.5, 64),
        (2.0, 67),
        (2.5, 72),
        (3.0, 67),
        (3.5, 64),
    ]
    right = next(part for part in scored.score.parts if part.id == "right-hand")
    left = next(part for part in scored.score.parts if part.id == "left-hand")
    for measure_index in range(14):
        right_actual = sorted(
            (float(item.offset), item.pitch.midi)
            for item in list(right.getElementsByClass(stream.Measure))[measure_index]
            .recurse()
            .notes
        )
        left_actual = sorted(
            (float(item.offset), item.pitch.midi)
            for item in list(left.getElementsByClass(stream.Measure))[measure_index].recurse().notes
        )
        assert right_actual == right_expected
        assert left_actual == left_expected

        left_rests = [
            (float(item.offset), float(item.quarterLength))
            for item in list(left.getElementsByClass(stream.Measure))[measure_index]
            .recurse()
            .getElementsByClass(note.Rest)
        ]
        assert left_rests == [(1.0, 3.0)]

    assert [event.hand for event in scored.notation_notes[-7:]] == [
        "left",
        "left",
        "right",
        "right",
        "right",
        "right",
        "right",
    ]
    final_right = list(right.getElementsByClass(stream.Measure))[-1]
    final_left = list(left.getElementsByClass(stream.Measure))[-1]
    assert [item.pitch.midi for item in final_right.recurse().notes] == [60, 64, 67, 72, 67]
    assert [item.pitch.midi for item in final_left.recurse().notes] == [48, 55]


def test_loud_simple_arpeggio_does_not_receive_mp() -> None:
    pattern = (48, 55, 60, 64, 67, 72, 67, 64)
    scored = build_score(
        [
            NoteEvent(index * 0.25, index * 0.25 + 0.2, pitch, 127, 0.99)
            for index, pitch in enumerate(pattern)
        ]
    )

    assert scored.reconstruction["voicing"]["strategy"] == "simple_arpeggio_stable_zone"
    assert list(scored.score.recurse().getElementsByClass(dynamics.Dynamic)) == []


def test_plain_parts_cannot_masquerade_as_a_piano_staff_group() -> None:
    score = stream.Score()
    right = stream.Part(id="right")
    left = stream.Part(id="left")
    score.insert(0, right)
    score.insert(0, left)
    score.insert(0, layout.StaffGroup([right, left], symbol="brace", barTogether=True))

    assert "EXPECTED_PIANO_PART_STAVES" in score_structure_errors(score)


@pytest.mark.parametrize(
    ("mutator", "expected_error"),
    [
        ("duplicate_part", "EXPECTED_ONE_PIANO_PART"),
        ("duplicate_part", "EXPECTED_ONE_PIANO_SCORE_PART"),
        ("double_treble", "EXPECTED_TREBLE_AND_BASS_CLEFS"),
        ("missing_note_staff", "INVALID_PIANO_NOTE_STAFF"),
        ("cross_staff_pedal", "INVALID_PIANO_PEDAL_MARK"),
    ],
)
def test_musicxml_reader_rejects_invalid_piano_layouts(
    tmp_path, mutator: str, expected_error: str
) -> None:
    destination = _write_valid_musicxml(tmp_path)
    tree = ElementTree.parse(destination)
    root = tree.getroot()
    if mutator == "duplicate_part":
        score_part = deepcopy(root.find("./part-list/score-part"))
        part = deepcopy(root.find("./part"))
        assert score_part is not None and part is not None
        score_part.set("id", "P2")
        part.set("id", "P2")
        root.find("./part-list").append(score_part)
        root.append(part)
    elif mutator == "double_treble":
        bass_clef = root.find("./part/measure/attributes/clef[@number='2']")
        assert bass_clef is not None
        bass_clef.find("./sign").text = "G"
        bass_clef.find("./line").text = "2"
    elif mutator == "missing_note_staff":
        notation = root.find("./part/measure/note")
        assert notation is not None
        notation.remove(notation.find("./staff"))
    else:
        measure = root.find("./part/measure")
        assert measure is not None
        _append_pedal_direction(measure, "start", "1")
        _append_pedal_direction(measure, "stop", "2")
    tree.write(destination, encoding="utf-8", xml_declaration=True)

    with pytest.raises(ValueError, match=expected_error):
        read_musicxml_structure(destination)


def test_reconstruction_failure_returns_explicit_basic_score_fallback(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        "app.pipeline.score._build_reconstructed_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid voices")),
    )

    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0.5, 1.5, 64, 90, 0.9),
        ]
    )
    paths = artifact_paths(tmp_path)
    write_timeline(scored, paths["timeline"])
    timeline = json.loads(paths["timeline"].read_text(encoding="utf-8"))

    assert scored.reconstruction["status"] == "fallback"
    assert scored.reconstruction["error_code"] == "SCORE_RECONSTRUCTION_FAILED"
    assert SCORE_RECONSTRUCTION_FALLBACK in scored.quality_flags
    assert timeline["reconstruction"]["fallback_used"] is True
    assert score_structure_errors(scored.score) == []


def test_reconstruction_programming_error_is_not_hidden_by_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.pipeline.score._build_reconstructed_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken code")),
    )

    with pytest.raises(RuntimeError, match="broken code"):
        build_score([NoteEvent(0, 1, 60, 90, 0.9)])


def test_musicxml_loads_in_osmd_and_an_independent_xml_parser(tmp_path) -> None:
    destination = tmp_path / "parser-check.musicxml"
    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0, 1, 64, 90, 0.9),
        ]
    )
    write_musicxml(scored, destination)

    result = validate_external_parsers([destination])[str(destination.resolve())]

    assert result["xmllint"]["status"] == "passed"
    assert result["osmd"]["status"] == "passed"
    assert result["osmd"]["measure_count"] >= 1
    assert result["osmd"]["svg_count"] >= 1


def test_external_parser_results_keep_duplicate_basenames_separate(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first" / "score.musicxml"
    second = tmp_path / "second" / "score.musicxml"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("<score-partwise/>", encoding="utf-8")
    second.write_text("<score-partwise/>", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.score_parser_validation._validate_xmllint",
        lambda path: {"status": "passed", "source": str(path)},
    )
    monkeypatch.setattr(
        "scripts.score_parser_validation._validate_osmd",
        lambda paths: {str(path): {"status": "passed", "source": str(path)} for path in paths},
    )

    result = validate_external_parsers([first, second])

    assert set(result) == {str(first.resolve()), str(second.resolve())}
    assert result[str(first.resolve())]["osmd"]["source"] == str(first.resolve())
    assert result[str(second.resolve())]["osmd"]["source"] == str(second.resolve())


def _write_valid_musicxml(tmp_path: Path) -> Path:
    destination = tmp_path / "valid.musicxml"
    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0, 1, 64, 90, 0.9),
        ]
    )
    write_musicxml(scored, destination)
    return destination


def _append_pedal_direction(measure: ElementTree.Element, action: str, staff: str) -> None:
    direction = ElementTree.SubElement(measure, "direction")
    direction_type = ElementTree.SubElement(direction, "direction-type")
    ElementTree.SubElement(
        direction_type,
        "pedal",
        {"number": "1", "type": action, "line": "yes"},
    )
    ElementTree.SubElement(direction, "staff").text = staff
