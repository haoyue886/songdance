import json

import pytest
from music21 import note, stream

from scripts import rebuild_review_isolated as builder
from scripts.compare_rebuilt_reviews import xml_signature
from scripts.human_quality_gate import file_sha256


def test_failure_stays_in_isolated_output_and_original_reviews_do_not_change(tmp_path, monkeypatch):
    original = {
        name: file_sha256(builder.SOURCE / name)
        for name in ("human-review.json", "structure-review.json")
    }

    def fail():
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(builder.structure, "run", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        builder.run(tmp_path / "isolated")
    state = json.loads((tmp_path / "isolated/rebuild.json").read_text())
    assert state["status"] == "failed" and state["stage"] == "structure"
    assert all(file_sha256(builder.SOURCE / name) == digest for name, digest in original.items())
    with pytest.raises(FileExistsError):
        builder.run(tmp_path / "isolated")


def test_xml_comparison_catches_note_duration_and_rest_changes(tmp_path):
    def write(name, duration, pitch):
        score = stream.Score()
        part = stream.Part()
        part.append(note.Note(pitch, quarterLength=duration))
        part.append(note.Rest(quarterLength=4 - duration))
        score.insert(0, part)
        path = tmp_path / name
        score.write("musicxml", fp=str(path))
        return path

    a = write("a.xml", 1, 60)
    b = write("b.xml", 1, 60)
    c = write("c.xml", 2, 60)
    d = write("d.xml", 1, 62)
    assert xml_signature(a) == xml_signature(b)
    assert xml_signature(a) != xml_signature(c)
    assert xml_signature(a) != xml_signature(d)


def test_actual_rebuild_binds_current_pipeline_without_copying_old_ratings():
    from scripts.human_quality_gate import compute_suite_fingerprint
    from scripts.structure_quality_gate import compute_structure_suite_fingerprint

    root = builder.SOURCE / "candidates/closeout-review-20260922-final"
    state = json.loads((root / "rebuild.json").read_text())
    assert state["status"] == "complete_pending_review"
    for name, digest in state["old_review_sha256"].items():
        assert file_sha256(builder.SOURCE / name) == digest
    for suite, compute in (
        ("human", compute_suite_fingerprint),
        ("structure", compute_structure_suite_fingerprint),
    ):
        review = json.loads((root / f"{suite}-review.json").read_text())
        assert review["suite_fingerprint"] == compute(root)
        assert all(row["rating"] == "pending" for row in review["results"])
        assert review["reviewer"]["midi_daw_experience"] is None
    differences = json.loads((root / "differences.json").read_text())
    assert len(differences["cases"]) == 26
    assert all(row["raw_events_equal"] for row in differences["cases"])
    changed = [
        row["case_id"]
        for row in differences["cases"]
        if not row["score_events_equal"] or not row["xml_note_rest_timing_equal"]
    ]
    assert set(changed) == {
        "01-slow-melody",
        "02-fast-scale",
        "03-block-chords",
        "04-arpeggios",
        "05-two-hand",
        "06-sustain",
        "07-soft",
        "08-dynamics",
        "09-light-noise",
        "10-device",
        "11-waltz-34",
        "12-compound-68",
        "13-key-change",
        "14-hand-crossing",
        "16-noisy-polyphony",
    }
    # The previous comparison remains historical evidence, not a current-code binding.
    historical = json.loads(
        (builder.SOURCE / "candidates/closeout-review-20260919-v1/differences.json").read_text()
    )
    assert [
        row["case_id"]
        for row in historical["cases"]
        if not row["score_events_equal"] or not row["xml_note_rest_timing_equal"]
    ] == ["14-hand-crossing"]
