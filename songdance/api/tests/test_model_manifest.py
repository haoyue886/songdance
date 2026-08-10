import json
from pathlib import Path

from scripts.evaluate_models import candidate_prechecks


def test_aria_amt_manifest_pins_the_verified_weight() -> None:
    manifest_path = Path(__file__).parents[1] / "experiments/models/manifest.json"
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))["candidates"][0]

    assert candidate["status"] == "research_only"
    assert candidate["source"]["commit"] == "a1ab73fc901d1759ec3bc173c146b3c6a3040261"
    assert candidate["weight"]["revision"] == "8cc4cf5c83b47f2689ac256a947b2a57c17a4c8b"
    assert candidate["weight"]["sha256"] == (
        "089d3129dbe93246aeda55efe668c8a48af08afaf9dd15c64cef0a07c0fb30a4"
    )


def test_aria_amt_manifest_records_cuda_only_inference() -> None:
    manifest_path = Path(__file__).parents[1] / "experiments/models/manifest.json"
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))["candidates"][0]

    assert candidate["runtime"]["accelerator"] == "nvidia_cuda"
    assert candidate["runtime"]["cpu_inference_supported"] is False
    assert candidate["production_eligibility"] == {
        "status": "blocked",
        "reason": "WEIGHT_LICENSE_NONCOMMERCIAL",
    }


def test_manifest_blocks_piano_transcription_inference_before_evaluation() -> None:
    manifest_path = Path(__file__).parents[1] / "experiments/models/manifest.json"
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))["candidates"][1]

    assert candidate["id"] == "piano_transcription_inference"
    assert candidate["status"] == "research_only"
    assert candidate["production_eligibility"] == {
        "status": "blocked",
        "reason": "SOURCE_LICENSE_TEXT_UNAVAILABLE",
    }
    assert candidate["weight"]["license"] == "CC-BY-4.0"
    assert candidate["training_data"]["license"] == "UNVERIFIED"


def test_manifest_blocks_omnizart_piano_before_evaluation() -> None:
    manifest_path = Path(__file__).parents[1] / "experiments/models/manifest.json"
    candidate = json.loads(manifest_path.read_text(encoding="utf-8"))["candidates"][2]

    assert candidate["id"] == "omnizart_piano"
    assert candidate["source"]["commit"] == "bcd8cb44d4da66ce87df10b6abee5c35a8cc2886"
    assert candidate["source"]["license"] == "MIT"
    assert candidate["weight"]["license"] == "UNVERIFIED"
    assert candidate["training_data"]["license"] == "UNVERIFIED"
    assert candidate["status"] == "research_only"
    assert candidate["production_eligibility"] == {
        "status": "blocked",
        "reason": "WEIGHT_AND_TRAINING_DATA_LICENSE_UNVERIFIED",
    }


def test_candidate_precheck_blocks_current_research_only_candidates() -> None:
    manifest_path = Path(__file__).parents[1] / "experiments/models/manifest.json"

    assert candidate_prechecks(manifest_path) == [
        {
            "candidate_id": "aria_amt",
            "artifact_status": "blocked",
            "evaluation_status": "research_only",
            "production_status": "blocked",
            "production_reason": "WEIGHT_LICENSE_NONCOMMERCIAL",
            "reason": "WEIGHT_LICENSE_NONCOMMERCIAL",
            "missing_fields": "",
        },
        {
            "candidate_id": "piano_transcription_inference",
            "artifact_status": "blocked",
            "evaluation_status": "research_only",
            "production_status": "blocked",
            "production_reason": "SOURCE_LICENSE_TEXT_UNAVAILABLE",
            "reason": "SOURCE_LICENSE_TEXT_UNAVAILABLE",
            "missing_fields": "",
        },
        {
            "candidate_id": "omnizart_piano",
            "artifact_status": "blocked",
            "evaluation_status": "research_only",
            "production_status": "blocked",
            "production_reason": "WEIGHT_AND_TRAINING_DATA_LICENSE_UNVERIFIED",
            "reason": "WEIGHT_AND_TRAINING_DATA_LICENSE_UNVERIFIED",
            "missing_fields": "",
        },
    ]


def test_aria_amt_has_an_isolated_container_definition() -> None:
    experiment_root = Path(__file__).parents[1] / "experiments/models/aria_amt"
    dockerfile = (experiment_root / "Dockerfile").read_text(encoding="utf-8")
    requirements = (experiment_root / "requirements.txt").read_text(encoding="utf-8")
    source_fetcher = (experiment_root / "fetch_pinned_source.py").read_text(encoding="utf-8")

    assert "FROM python:3.11.12-slim-bookworm" in dockerfile
    assert "torch==2.4.1 torchaudio==2.4.1" in dockerfile
    assert "libgomp1" in dockerfile
    assert "a1ab73fc901d1759ec3bc173c146b3c6a3040261" in source_fetcher
    assert "git_blob_sha1" in source_fetcher
    assert "aria-utils/archive/4ed0749d2d70918610f03a5316bf283479ff9d09.tar.gz" in requirements
