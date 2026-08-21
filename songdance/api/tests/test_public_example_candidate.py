import json
import shutil
from pathlib import Path

import pytest

from app.pipeline.score import read_musicxml_structure
from scripts import build_public_example_candidate_review as review_builder
from scripts.human_quality_gate import file_sha256

CANDIDATE_ROOT = Path(__file__).parent / "fixtures/audio/public-example-candidates/petzold-minuet"


def test_petzold_candidate_is_provenance_bound_and_pending() -> None:
    manifest = json.loads((CANDIDATE_ROOT / "candidate.json").read_text(encoding="utf-8"))

    assert manifest["candidate_id"] == "petzold-minuet-bwv-anh-114"
    assert manifest["status"] == "candidate_pending"
    assert manifest["review"]["rating"] == "pending"
    assert manifest["source"]["clip_duration_sec"] <= 90
    assert manifest["source"]["clip_sha256"] == file_sha256(CANDIDATE_ROOT / "source.wav")

    reference = manifest["reference_score"]
    assert reference["parts"] == 2
    assert reference["measure_count"] == 32
    assert reference["notation_key_signature"] == ["G major"]
    assert reference["time_signature"] == ["3/4"]
    assert reference["shortest_note_value"] == 16
    assert reference["midi_sha256"] == file_sha256(CANDIDATE_ROOT / "reference.mid")
    assert reference["pdf_sha256"] == file_sha256(CANDIDATE_ROOT / "reference.pdf")

    analysis = manifest["pipeline"]["analysis"]
    notation = manifest["pipeline"]["notation"]
    override = manifest["pipeline"]["analysis_override"]
    assert analysis["time_signature"] == "4/4"
    assert notation["notation_time_signature"] == "3/4"
    assert override == {
        "detected_time_signature": "4/4",
        "detected_time_signature_source": "default",
        "detected_time_signature_confidence": analysis["time_signature_confidence"],
        "notation_time_signature": "3/4",
        "notation_time_signature_source": "reference_score",
        "notation_time_signature_confidence": 1.0,
    }
    assert manifest["pipeline"]["structure"]["errors"] == []
    assert manifest["pipeline"]["parser_validation"]["xmllint"]["status"] == "passed"
    assert manifest["pipeline"]["parser_validation"]["osmd"]["status"] == "passed"

    actual_structure = read_musicxml_structure(CANDIDATE_ROOT / "score.musicxml")
    assert actual_structure["errors"] == []
    assert actual_structure["part_count"] == 1
    assert actual_structure["staff_count"] == 2
    assert actual_structure["measure_count"] == 32
    assert actual_structure["time_signatures"] == ["3/4"]

    for artifact in manifest["artifacts"].values():
        assert artifact["sha256"] == file_sha256(CANDIDATE_ROOT / artifact["path"])


def test_review_package_rejects_non_pending_candidate(tmp_path: Path) -> None:
    candidate_root = tmp_path / "candidate"
    shutil.copytree(CANDIDATE_ROOT, candidate_root)
    manifest_path = candidate_root / "candidate.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "approved"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    original_root = review_builder.CANDIDATE_ROOT
    review_builder.CANDIDATE_ROOT = candidate_root
    try:
        with pytest.raises(ValueError, match="candidate_pending"):
            review_builder.build_package(tmp_path / "dist")
    finally:
        review_builder.CANDIDATE_ROOT = original_root
