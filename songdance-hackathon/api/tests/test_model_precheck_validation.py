import hashlib
import json
from pathlib import Path

import pytest

from scripts.evaluate_models import candidate_prechecks
from tests.model_audit import production_audit


def test_candidate_precheck_requires_explicit_production_use_verification(
    tmp_path: Path,
) -> None:
    weight_path = tmp_path / "model.safetensors"
    weight_path.write_bytes(b"model")
    audit = production_audit()
    training_data = audit["training_data"]
    assert isinstance(training_data, dict)
    training_data["production_use_verified"] = False
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "eligible", "reason": ""},
                **audit,
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

    with pytest.raises(ValueError, match="training data must explicitly verify production use"):
        candidate_prechecks(path)


def test_candidate_precheck_requires_training_data_audit_for_blocked_candidate(
    tmp_path: Path,
) -> None:
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "research_only",
                "production_eligibility": {"status": "blocked", "reason": "SOURCE_UNVERIFIED"},
                "source": production_audit()["source"],
                "weight": {
                    "revision": "unverified",
                    "sha256": "unverified",
                    "license": "CC-BY-4.0",
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

    with pytest.raises(ValueError, match="must define training data audit"):
        candidate_prechecks(path)


def test_candidate_precheck_enforces_research_only_before_weight_precheck(
    tmp_path: Path,
) -> None:
    manifest = {
        "schema_version": 1,
        "candidates": [
            {
                "id": "candidate",
                "status": "not_evaluated",
                "production_eligibility": {"status": "blocked", "reason": "SOURCE_UNVERIFIED"},
                **production_audit(),
                "weight": {},
            }
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="blocked production eligibility must be research only"):
        candidate_prechecks(path)


def test_candidate_precheck_rejects_noncommercial_weight_for_production(
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
                    "license": "CC-BY-NC-SA-4.0",
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


def test_candidate_precheck_requires_noncommercial_weight_to_be_research_only(
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
                "production_eligibility": {
                    "status": "blocked",
                    "reason": "WEIGHT_LICENSE_NONCOMMERCIAL",
                },
                **production_audit(),
                "weight": {
                    "revision": "1" * 40,
                    "sha256": hashlib.sha256(weight_path.read_bytes()).hexdigest(),
                    "license": "CC-BY-NC-SA-4.0",
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

    with pytest.raises(ValueError, match="blocked production eligibility must be research only"):
        candidate_prechecks(path)


def test_candidate_precheck_rejects_an_empty_candidate_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"schema_version": 1, "candidates": []}), encoding="utf-8")

    with pytest.raises(ValueError, match="at least one candidate"):
        candidate_prechecks(path)
