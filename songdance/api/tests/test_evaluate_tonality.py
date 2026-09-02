import hashlib
from pathlib import Path

import pytest

from scripts.evaluate_tonality import score_predictions, validate_manifest


def _case(case_id: str, kind: str = "controlled_adversarial") -> dict[str, object]:
    digest = hashlib.sha256(case_id.encode()).hexdigest()
    return {
        "id": case_id,
        "kind": kind,
        "audio_sha256": digest,
        "reference_score_sha256": digest,
        "license": "CC0-1.0",
        "local_tonality": "C major",
        "notation_key_signature": "C major",
        "human_verified": True,
        "audio_path": f"audio/{case_id}.wav",
        "reference_score_path": f"scores/{case_id}.mid",
        "reviewer_id": "expert-1",
        "phrase_boundaries": [0, 1],
        "cadence_type": "none",
        "tonicization_or_modulation": "none",
    }


def test_manifest_requires_twenty_cases_and_twelve_real_recordings(tmp_path: Path) -> None:
    manifest = {"cases": [_case(str(index)) for index in range(20)]}

    with pytest.raises(ValueError, match="real public recordings"):
        validate_manifest(manifest, asset_root=tmp_path)

    for index in range(12):
        manifest["cases"][index] = _case(str(index), "real_public_recording")
    for case in manifest["cases"]:
        audio = tmp_path / case["audio_path"]
        score = tmp_path / case["reference_score_path"]
        audio.parent.mkdir(parents=True, exist_ok=True)
        score.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(case["id"].encode())
        score.write_bytes(case["id"].encode())
        case["audio_sha256"] = hashlib.sha256(audio.read_bytes()).hexdigest()
        case["reference_score_sha256"] = hashlib.sha256(score.read_bytes()).hexdigest()
    assert len(validate_manifest(manifest, asset_root=tmp_path)) == 20


def test_prediction_metrics_include_top_two_and_notation_error_rate(tmp_path: Path) -> None:
    cases = [_case(str(i)) for i in range(20)]
    for case in cases[:12]:
        case["kind"] = "real_public_recording"
    predictions = {
        case["id"]: {
            "candidates": [
                {"value": "C major", "score": 0.8},
                {"value": "G major", "score": 0.2},
            ],
            "notation_eligible": True,
            "notation_key_signature": "C major",
        }
        for case in cases
    }

    for case in cases:
        audio = tmp_path / case["audio_path"]
        score = tmp_path / case["reference_score_path"]
        audio.parent.mkdir(parents=True, exist_ok=True)
        score.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(case["id"].encode())
        score.write_bytes(case["id"].encode())
        case["audio_sha256"] = hashlib.sha256(audio.read_bytes()).hexdigest()
        case["reference_score_sha256"] = hashlib.sha256(score.read_bytes()).hexdigest()
    result = score_predictions(cases, predictions, asset_root=tmp_path)

    assert result["top1_accuracy"] == 1.0
    assert result["top2_recall"] == 1.0
    assert result["notation_error_rate"] == 0.0
    assert result["passed"] is True
