import hashlib
import json
from pathlib import Path

import pytest

from scripts.evaluate_models import candidate_prechecks
from tests.model_audit import production_audit


def test_candidate_precheck_allows_a_verified_weight(tmp_path: Path) -> None:
    weights = tmp_path / "weights"
    weights.mkdir()
    weight_path = weights / "model.safetensors"
    weight_path.write_bytes(b"verified model")
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **production_audit(),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
                    "license": "Apache-2.0",
                    "production_use_verified": True,
                    "license_evidence_url": "https://example.com/license",
                    "source_url": "https://example.com/model",
                    "local_path": "weights/model.safetensors",
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    assert candidate_prechecks(path) == [
        {
            "candidate_id": "candidate",
            "artifact_status": "ready",
            "evaluation_status": "not_evaluated",
            "production_status": "eligible",
            "production_reason": "",
            "reason": "",
            "missing_fields": "",
        }
    ]


def test_candidate_precheck_rejects_a_weight_with_the_wrong_digest(tmp_path: Path) -> None:
    weight_path = tmp_path / "model.safetensors"
    weight_path.write_bytes(b"actual model")
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **production_audit(),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": "2" * 64,
                    "license": "Apache-2.0",
                    "production_use_verified": True,
                    "license_evidence_url": "https://example.com/license",
                    "source_url": "https://example.com/model",
                    "local_path": "model.safetensors",
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = candidate_prechecks(path)[0]
    assert result["artifact_status"] == "blocked"
    assert result["reason"] == "WEIGHT_CHECKSUM_MISMATCH"


def test_candidate_precheck_rejects_a_non_hex_source_commit(tmp_path: Path) -> None:
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **production_audit(commit="z" * 40),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": "2" * 64,
                    "license": "Apache-2.0",
                    "production_use_verified": True,
                    "license_evidence_url": "https://example.com/license",
                    "source_url": "https://example.com/model",
                    "local_path": "model.safetensors",
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="full source commit"):
        candidate_prechecks(path)


def test_candidate_precheck_rejects_research_only_candidate_marked_eligible(
    tmp_path: Path,
) -> None:
    weight_path = tmp_path / "model.safetensors"
    weight_path.write_bytes(b"model")
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "research_only",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **production_audit(),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
                    "license": "Apache-2.0",
                    "production_use_verified": True,
                    "license_evidence_url": "https://example.com/license",
                    "source_url": "https://example.com/model",
                    "local_path": "model.safetensors",
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="research only status must block production"):
        candidate_prechecks(path)


def test_candidate_precheck_rejects_research_limited_license_for_production(
    tmp_path: Path,
) -> None:
    weight_path = tmp_path / "model.safetensors"
    weight_path.write_bytes(b"model")
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **production_audit(),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
                    "license": "NON-COMMERCIAL-RESEARCH-ONLY",
                    "production_use_verified": True,
                    "license_evidence_url": "https://example.com/license",
                    "source_url": "https://example.com/model",
                    "local_path": "model.safetensors",
                },
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="weight license does not permit production"):
        candidate_prechecks(path)
