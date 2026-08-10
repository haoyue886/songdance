import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

MANIFEST_PATH = Path(__file__).parents[1] / "experiments/models/manifest.json"
REQUIRED_WEIGHT_FIELDS = (
    "revision",
    "sha256",
    "license",
    "license_evidence_url",
    "source_url",
    "local_path",
)
REQUIRED_SOURCE_FIELDS = (
    "repository",
    "commit",
    "license",
    "license_evidence_url",
)
REQUIRED_TRAINING_DATA_FIELDS = (
    "summary",
    "license",
    "license_evidence_url",
)
EVALUATION_STATUSES = {"not_evaluated", "evaluated", "research_only"}


def candidate_prechecks(manifest_path: Path = MANIFEST_PATH) -> list[dict[str, str]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidates = manifest.get("candidates")
    if manifest.get("schema_version") != 1 or not isinstance(candidates, list):
        raise ValueError("candidate manifest must use schema version 1 and contain candidates")
    if not candidates:
        raise ValueError("candidate manifest must contain at least one candidate")

    return [_candidate_precheck(candidate, manifest_path.parent) for candidate in candidates]


def _candidate_precheck(candidate: Any, manifest_root: Path) -> dict[str, str]:
    if not isinstance(candidate, dict):
        raise ValueError("candidate manifest entries must be objects")
    candidate_id = candidate.get("id")
    evaluation_status = candidate.get("status")
    production = candidate.get("production_eligibility")
    source = candidate.get("source")
    weight = candidate.get("weight")
    if (
        not isinstance(candidate_id, str)
        or not isinstance(evaluation_status, str)
        or not isinstance(production, dict)
        or not isinstance(source, dict)
        or not isinstance(weight, dict)
    ):
        raise ValueError(
            "candidate must define id, status, production eligibility, source, and weight"
        )
    production_status = production.get("status")
    production_reason = production.get("reason")
    if evaluation_status not in EVALUATION_STATUSES:
        raise ValueError(f"{candidate_id} must define a valid evaluation status")
    if production_status not in {"eligible", "blocked"} or not isinstance(
        production_reason, str
    ):
        raise ValueError(f"{candidate_id} must define a valid production eligibility")
    if production_status == "blocked" and not production_reason:
        raise ValueError(f"{candidate_id} blocked production eligibility needs a reason")
    missing_source = [field for field in REQUIRED_SOURCE_FIELDS if not source.get(field)]
    if missing_source:
        raise ValueError(f"{candidate_id} source audit is missing: {','.join(missing_source)}")
    if not _is_hex(source.get("commit"), 40):
        raise ValueError(f"{candidate_id} must use a full source commit")
    if not _is_https_url(source.get("repository")):
        raise ValueError(f"{candidate_id} must define an HTTPS source repository")
    if not _is_https_url(source.get("license_evidence_url")):
        raise ValueError(f"{candidate_id} must define an HTTPS source license evidence URL")

    training_data = candidate.get("training_data")
    if not isinstance(training_data, dict):
        raise ValueError(f"{candidate_id} must define training data audit")
    missing_training_data = [
        field for field in REQUIRED_TRAINING_DATA_FIELDS if not training_data.get(field)
    ]
    if missing_training_data:
        raise ValueError(
            f"{candidate_id} training data audit is missing: {','.join(missing_training_data)}"
        )
    if not _is_https_url(training_data.get("license_evidence_url")):
        raise ValueError(
            f"{candidate_id} must define an HTTPS training data license evidence URL"
        )

    if evaluation_status == "research_only" and production_status != "blocked":
        raise ValueError(f"{candidate_id} research only status must block production")
    if production_status == "blocked" and evaluation_status != "research_only":
        raise ValueError(f"{candidate_id} blocked production eligibility must be research only")

    missing = [field for field in REQUIRED_WEIGHT_FIELDS if not weight.get(field)]
    if missing:
        return _precheck_result(
            candidate_id,
            evaluation_status,
            production_status,
            production_reason,
            "blocked",
            "WEIGHT_PROVENANCE_UNVERIFIED",
            ",".join(missing),
        )
    if not _is_https_url(weight.get("source_url")):
        raise ValueError(f"{candidate_id} must define an HTTPS weight source URL")
    if not _is_https_url(weight.get("license_evidence_url")):
        raise ValueError(f"{candidate_id} must define an HTTPS license evidence URL")

    if production_status == "blocked":
        return _precheck_result(
            candidate_id,
            evaluation_status,
            production_status,
            production_reason,
            "blocked",
            production_reason,
        )

    _require_production_use(candidate_id, "source", source)
    _require_production_use(candidate_id, "training data", training_data)
    _require_production_use(candidate_id, "weight", weight)
    if not _is_hex(weight["revision"], 40):
        raise ValueError(f"{candidate_id} weight revision must be a full commit")
    if not _is_hex(weight["sha256"], 64):
        raise ValueError(f"{candidate_id} weight sha256 must be a SHA-256 digest")

    weight_path = _weight_path(manifest_root, weight["local_path"])
    if not weight_path.is_file():
        return _precheck_result(
            candidate_id,
            evaluation_status,
            production_status,
            production_reason,
            "blocked",
            "WEIGHT_FILE_UNAVAILABLE",
        )
    if _file_sha256(weight_path) != weight["sha256"]:
        return _precheck_result(
            candidate_id,
            evaluation_status,
            production_status,
            production_reason,
            "blocked",
            "WEIGHT_CHECKSUM_MISMATCH",
        )
    return _precheck_result(
        candidate_id,
        evaluation_status,
        production_status,
        production_reason,
        "ready",
        "",
    )


def _precheck_result(
    candidate_id: str,
    evaluation_status: str,
    production_status: str,
    production_reason: str,
    artifact_status: str,
    reason: str,
    missing_fields: str = "",
) -> dict[str, str]:
    return {
        "candidate_id": candidate_id,
        "artifact_status": artifact_status,
        "evaluation_status": evaluation_status,
        "production_status": production_status,
        "production_reason": production_reason,
        "reason": reason,
        "missing_fields": missing_fields,
    }


def _is_hex(value: object, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and all(
        character in "0123456789abcdef" for character in value
    )


def _is_https_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _require_production_use(
    candidate_id: str, component_name: str, component: dict[str, object]
) -> None:
    license_name = component["license"]
    if not _is_production_license(license_name):
        raise ValueError(f"{candidate_id} {component_name} license does not permit production")
    if component.get("production_use_verified") is not True:
        raise ValueError(
            f"{candidate_id} {component_name} must explicitly verify production use"
        )


def _is_production_license(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = "".join(character for character in value.upper() if character.isalnum())
    prohibited_markers = ("NC", "NONCOMMERCIAL", "RESEARCH", "NONPRODUCTION")
    return normalized not in {"", "UNKNOWN", "UNVERIFIED"} and not any(
        marker in normalized for marker in prohibited_markers
    )


def _weight_path(manifest_root: Path, local_path: str) -> Path:
    relative = Path(local_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("weight local_path must stay inside the experiment directory")
    root = manifest_root.resolve()
    destination = (root / relative).resolve()
    if root not in destination.parents:
        raise ValueError("weight local_path must stay inside the experiment directory")
    return destination


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    prechecks = candidate_prechecks()
    print(json.dumps(prechecks, ensure_ascii=False, indent=2))
    return 0 if all(item["artifact_status"] == "ready" for item in prechecks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
