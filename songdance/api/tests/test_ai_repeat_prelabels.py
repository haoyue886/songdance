import json

import pytest

from scripts.build_ai_repeat_prelabels import build


def test_prelabels_are_pending_and_non_authoritative(tmp_path):
    annotation = tmp_path / "annotation"
    annotation.mkdir()
    (annotation / "manifest.json").write_text(json.dumps({"candidates": []}))
    (annotation / "labels.json").write_text(json.dumps({"manifest_sha256": "bad", "labels": []}))
    with pytest.raises((ValueError, FileNotFoundError)):
        build(annotation, tmp_path / "missing.json", tmp_path / "out")


def test_existing_evidence_reproduces_pending_draft(tmp_path):
    from pathlib import Path

    root = Path(__file__).parent / "fixtures/audio/candidates"
    annotation = root / "real-repeat-annotations-v2"
    before = (annotation / "labels.json").read_bytes()
    result = build(annotation, root / "real-partial-probe-v1/audit.json", tmp_path / "out")
    stored = json.loads((root / "real-repeat-ai-prelabels-v1/ai-prelabels.json").read_text())
    assert result == stored
    assert result["counts"] == {"total": 120, "uncertain": 120, "no_restrike": 0}
    assert all(row["judgment"] == "pending" for row in result["suggestions"])
    assert not result["production_eligible"] and not result["deletion_authorized"]
    assert (annotation / "labels.json").read_bytes() == before
    with pytest.raises(FileExistsError):
        build(annotation, root / "real-partial-probe-v1/audit.json", tmp_path / "out")
