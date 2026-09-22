import json
import shutil

import pytest

from scripts.compare_piano_model_outputs import read_midi
from scripts.notate_transkun_candidate import melody_events, run
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256

RAW = ROOT / "tests/fixtures/audio/candidates/transkun-entry-smoke-07-v2"
SCORE = ROOT / "tests/fixtures/audio/candidates/transkun-notation-smoke-07-v2"


def test_actual_raw_to_notation_preserves_pitch_order_and_unknown_confidence():
    raw = json.loads((RAW / "raw-timeline.json").read_text())["notes"]
    timeline = json.loads((SCORE / "timeline.json").read_text())
    report = json.loads((SCORE / "notation.json").read_text())
    assert len(raw) == len(timeline["notes"]) == 40
    assert [n["pitch"] for n in raw] == [n["pitch"] for n in timeline["notes"]]
    assert all(n["confidence"] is None and n["hand_confidence"] is None for n in timeline["notes"])
    assert max(abs(c["onset_shift_seconds"]) for c in timeline["changes"]) < 0.05
    parsed = read_midi(SCORE / "score.mid")
    assert [(n["start_sec"], n["end_sec"], n["pitch"]) for n in parsed] == [
        (n["start_sec"], n["end_sec"], n["pitch"]) for n in timeline["notes"]
    ]
    assert report["structure"]["staff_count"] == 1
    assert report["structure"]["rest_count"] == 0
    assert report["structure"]["measure_duration_error_count"] == 0
    assert report["production_eligible"] is False
    for name, digest in report["artifacts_sha256"].items():
        assert file_sha256(SCORE / name) == digest


@pytest.mark.parametrize("case", ("06-sustain", "10-device", "14-hand-crossing"))
def test_polyphonic_raw_model_outputs_cannot_enter_monophonic_profile(case):
    notes = read_midi(BATCH_ROOT / case / "transkun-v2/raw.mid")
    with pytest.raises(ValueError, match="treble-only|simultaneous"):
        melody_events(notes)


def test_changed_raw_events_are_rejected_before_creating_score(tmp_path):
    source = tmp_path / "raw"
    shutil.copytree(RAW, source)
    (source / "raw-timeline.json").write_text("{}")
    with pytest.raises(ValueError, match="artifact changed"):
        run(source, tmp_path / "output", 120, "4/4")
    assert not (tmp_path / "output").exists()


def test_rebuild_has_same_semantic_notes_and_cannot_overwrite(tmp_path):
    output = tmp_path / "new"
    report = run(RAW, output, 120, "4/4")
    assert report["status"] == "complete_candidate_only"
    assert json.loads((output / "timeline.json").read_text()) == json.loads(
        (SCORE / "timeline.json").read_text()
    )
    with pytest.raises(FileExistsError):
        run(RAW, output, 120, "4/4")
