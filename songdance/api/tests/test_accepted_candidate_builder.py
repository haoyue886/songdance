import json
import shutil

import pytest

from scripts import build_reviewed_candidates as builder
from scripts.piano_comparison_cases import file_sha256


def test_accepted_versions_are_copied_without_rewriting_scores(tmp_path):
    output = tmp_path / "release"
    report = builder.build_accepted(output)
    assert report["production_eligible"] is False
    assert report["acceptance_source"] == "user_message"
    assert report["confirmation_text"] == "都没问题进行下一步"
    rows = {r["case_id"]: r for r in report["cases"]}
    assert len(rows) == 3
    for row in rows.values():
        assert row["status"] == "user_accepted_candidate"
        for item in row["files"].values():
            assert file_sha256(output / item["path"]) == item["sha256"]
    assert rows["06-sustain"]["source_kind"] == "new_synthetic_teacher_pattern_not_original_audio"
    assert rows["06-sustain"]["structure"]["chord_count"] == 15
    assert rows["07-soft"]["structure"]["staff_count"] == 1
    assert rows["10-device"]["known_limitations"]
    with pytest.raises(FileExistsError):
        builder.build_accepted(output)


def test_changed_accepted_audio_is_rejected_before_building(tmp_path):
    registry = json.loads(builder.ACCEPTANCE.read_text())
    for case in registry["cases"]:
        for item in case["files"].values():
            target = tmp_path / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(builder.PROJECT_ROOT / item["path"], target)
    artifact = registry["cases"][0]["files"]["source.wav"]
    (tmp_path / artifact["path"]).write_bytes(b"changed")
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="accepted artifact changed"):
        builder.build_accepted(output, project=tmp_path)
    assert not output.exists()


def test_candidate_confirmation_does_not_allow_production_flag(tmp_path):
    registry = json.loads(builder.ACCEPTANCE.read_text())
    registry["production_eligible"] = True
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(registry))
    with pytest.raises(ValueError, match="cannot enable production"):
        builder.build_accepted(tmp_path / "output", acceptance=path)


def test_failed_parser_is_not_reported_as_accepted_output(tmp_path, monkeypatch):
    def fail(*args):
        raise ValueError("controlled parse failure")

    monkeypatch.setattr(builder, "read_musicxml_structure", fail)
    with pytest.raises(ValueError, match="controlled"):
        builder.build_accepted(tmp_path / "output")
    manifest = json.loads((tmp_path / "output/manifest.json").read_text())
    assert manifest["status"] == "failed"
