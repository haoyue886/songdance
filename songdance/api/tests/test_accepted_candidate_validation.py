import json
import shutil

import pytest

from scripts.piano_comparison_cases import ROOT
from scripts.validate_accepted_candidates import validate

SOURCE = ROOT / "tests/fixtures/audio/candidates/accepted-candidates-v1"


def test_actual_accepted_candidates_validate_without_becoming_production_ready():
    report = validate(SOURCE)
    assert report["candidate_integrity_passed"] is True
    assert report["production_eligible"] is False
    assert len(report["cases"]) == 3
    device = next(row for row in report["cases"] if row["case_id"] == "10-device")
    assert device["known_limitations"]


@pytest.mark.parametrize(
    "change,pattern",
    [
        ("missing", "case set"),
        ("duplicate", "duplicate"),
        ("audio", "fingerprint"),
        ("limitations", "known_limitations"),
        ("production", "authorize production"),
        ("path", "artifact path"),
        ("structure", "parsed structure"),
    ],
)
def test_modified_release_inputs_are_rejected(tmp_path, change, pattern):
    root = tmp_path / "copy"
    shutil.copytree(SOURCE, root)
    path = root / "manifest.json"
    data = json.loads(path.read_text())
    if change == "missing":
        data["cases"].pop()
    elif change == "duplicate":
        data["cases"].append(data["cases"][0])
    elif change == "audio":
        (root / "06-sustain/source.wav").write_bytes(b"changed")
    elif change == "limitations":
        next(r for r in data["cases"] if r["case_id"] == "10-device")["known_limitations"] = []
    elif change == "production":
        data["production_eligible"] = True
    elif change == "path":
        data["cases"][0]["files"]["source.wav"]["path"] = "../source.wav"
    elif change == "structure":
        data["cases"][0]["structure"]["rest_count"] = 999
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=pattern):
        validate(root)
