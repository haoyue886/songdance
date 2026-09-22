import json
import shutil

import pytest

from scripts import build_reviewed_candidates as builder
from scripts.piano_comparison_cases import BATCH_ROOT, file_sha256


def test_full_rebuild_preserves_review_and_does_not_mark_failed_cases_passed(tmp_path):
    output = tmp_path / "candidates"
    report = builder.build(output)
    assert report["production_eligible"] is False
    cases = {r["case_id"]: r for r in report["cases"]}
    assert cases["06-sustain"]["status"] == "blocked"
    assert not (output / "06-sustain").exists()
    assert cases["07-soft"]["source_sha256"] == cases["07-soft"]["score_sha256"]
    assert cases["10-device"]["status"] == "needs_teacher_review_and_missing_bass_fix"
    assert len(cases["10-device"]["changes"]) == 26
    reference = BATCH_ROOT / "10-device/bass-rhythm-v2/score.musicxml"
    assert file_sha256(reference) == file_sha256(output / "10-device/score.musicxml")
    assert report["musescore_validation"].startswith("not_run")
    with pytest.raises(FileExistsError):
        builder.build(output)


def test_changed_reviewed_score_is_rejected_before_output(tmp_path):
    feedback = json.loads(builder.FEEDBACK.read_text())
    for entry in feedback["cases"]:
        p = tmp_path / entry["candidate_path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(builder.PROJECT_ROOT / entry["candidate_path"], p)
    (tmp_path / feedback["cases"][0]["candidate_path"]).write_text("changed")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="reviewed source changed"):
        builder.build(output, project=tmp_path)
    assert not output.exists()


def test_parser_failure_is_saved_without_success_state(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("controlled parse failure")

    monkeypatch.setattr(builder, "read_musicxml_structure", fail)
    with pytest.raises(ValueError, match="controlled"):
        builder.build(tmp_path / "output")
    manifest = json.loads((tmp_path / "output/manifest.json").read_text())
    assert manifest["status"] == "failed"
    assert manifest["production_eligible"] is False
