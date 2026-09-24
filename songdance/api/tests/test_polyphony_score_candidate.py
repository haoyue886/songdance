import json
from collections import Counter

import pretty_midi
import pytest
from music21 import meter, note, stream, tempo

from app.pipeline.transcribe import NoteEvent
from scripts import build_polyphony_score_candidate as builder
from scripts.compare_piano_model_outputs import read_midi
from scripts.validate_polyphony_preview import validate


def test_actual_polyphony_export_matches_all_events(tmp_path):
    output = tmp_path / "candidate"
    builder.run(output)
    report = json.loads((output / "audit.json").read_text())
    assert report["status"] == "preview_needs_review" and report["production_eligible"] is False
    assert report["export_consistency"]["checks"]["xml_matches_events"] is True
    assert report["export_consistency"]["checks"]["midi_matches_events"] is True
    assert report["export_consistency"]["expected_events"] == 149
    before = read_midi(builder.SOURCE / "candidate.mid")
    after = read_midi(output / "score.mid")
    assert Counter(n["pitch"] for n in before) == Counter(n["pitch"] for n in after)
    timeline = json.loads((output / "timeline.json").read_text())
    assert timeline["notation"]["notation_time_signature_confidence"] == 0
    assert (
        timeline["notation"]["notation_key_signature_source"]
        == "operator_display_default_not_inferred"
    )
    assert timeline["notation"]["notation_key_signature_confidence"] == 0


def test_consistency_gate_accepts_real_equal_export_and_rejects_duration_change(tmp_path):
    score = stream.Score()
    part = stream.Part()
    part.append(meter.TimeSignature("2/4"))
    part.append(tempo.MetronomeMark(number=60))
    part.append(note.Note(60, quarterLength=1))
    part.append(note.Rest(quarterLength=1))
    score.insert(0, part)
    xml = tmp_path / "score.musicxml"
    score.write("musicxml", fp=str(xml))
    midi = pretty_midi.PrettyMIDI(initial_tempo=60)
    piano = pretty_midi.Instrument(0)
    piano.notes = [pretty_midi.Note(80, 60, 0, 1)]
    midi.instruments.append(piano)
    mid = tmp_path / "score.mid"
    midi.write(str(mid))
    events = [NoteEvent(0, 1, 60, 80, 0)]
    assert validate(xml, mid, events, 1)["status"] == "passed"
    assert validate(xml, mid, [NoteEvent(0, 0.5, 60, 80, 0)], 1)["status"] == "failed"


def test_mismatch_gate_still_blocks_modified_xml(tmp_path, monkeypatch):
    from xml.etree import ElementTree as ET

    original = builder.write_musicxml

    def corrupt(scored, path):
        original(scored, path)
        tree = ET.parse(path)
        pitch = tree.find(".//note/pitch/step")
        pitch.text = "D" if pitch.text != "D" else "E"
        tree.write(path, encoding="utf-8", xml_declaration=True)

    monkeypatch.setattr(builder, "write_musicxml", corrupt)
    out = tmp_path / "bad"
    with pytest.raises(ValueError, match="event mismatch"):
        builder.run(out)
    assert json.loads((out / "audit.json").read_text())["status"] == "failed"
