"""Validate and score the independent local-tonality evaluation manifest."""

import hashlib
import json
from pathlib import Path
from statistics import mean

MIN_CASES = 20
MIN_REAL_CASES = 12
REAL_KIND = "real_public_recording"
REQUIRED_FIELDS = {
    "id",
    "kind",
    "audio_sha256",
    "reference_score_sha256",
    "license",
    "local_tonality",
    "notation_key_signature",
    "human_verified",
    "audio_path",
    "reference_score_path",
    "reviewer_id",
    "phrase_boundaries",
    "cadence_type",
    "tonicization_or_modulation",
}


def validate_manifest(
    manifest: dict[str, object], *, asset_root: Path
) -> list[dict[str, object]]:
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        raise ValueError("tonality manifest must contain a cases list")
    if len(cases) < MIN_CASES:
        raise ValueError(f"tonality manifest requires at least {MIN_CASES} cases")
    real_count = sum(
        isinstance(case, dict) and case.get("kind") == REAL_KIND for case in cases
    )
    if real_count < MIN_REAL_CASES:
        raise ValueError(
            f"tonality manifest requires at least {MIN_REAL_CASES} real public "
            f"recordings; found {real_count}"
        )
    normalized: list[dict[str, object]] = []
    ids: set[str] = set()
    for index, raw in enumerate(cases):
        if not isinstance(raw, dict):
            raise ValueError(f"tonality case {index} must be an object")
        missing = REQUIRED_FIELDS - set(raw)
        if missing:
            raise ValueError(f"tonality case {index} missing fields: {sorted(missing)}")
        case = dict(raw)
        case_id = case["id"]
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ValueError(f"tonality case {index} has invalid or duplicate id")
        ids.add(case_id)
        if case["kind"] not in {REAL_KIND, "controlled_adversarial"}:
            raise ValueError(f"tonality case {case_id} has unsupported kind")
        for field in ("audio_sha256", "reference_score_sha256"):
            value = case[field]
            if not isinstance(value, str) or len(value) != 64:
                raise ValueError(f"tonality case {case_id} has invalid {field}")
        for path_field, hash_field in (
            ("audio_path", "audio_sha256"),
            ("reference_score_path", "reference_score_sha256"),
        ):
            path_value = case[path_field]
            if not isinstance(path_value, str) or Path(path_value).is_absolute():
                raise ValueError(f"tonality case {case_id} has invalid {path_field}")
            root = asset_root.resolve()
            asset = (root / path_value).resolve()
            if root not in asset.parents or asset.is_symlink():
                raise ValueError(f"tonality case {case_id} {path_field} escapes asset root")
            if not asset.is_file() or _file_sha256(asset) != case[hash_field]:
                raise ValueError(f"tonality case {case_id} {path_field} hash mismatch")
        if not isinstance(case["license"], str) or not case["license"]:
            raise ValueError(f"tonality case {case_id} requires a license")
        if case["human_verified"] is not True:
            raise ValueError(f"tonality case {case_id} is not independently verified")
        if not isinstance(case["reviewer_id"], str) or not case["reviewer_id"]:
            raise ValueError(f"tonality case {case_id} requires reviewer_id")
        if not isinstance(case["phrase_boundaries"], list) or not case["phrase_boundaries"]:
            raise ValueError(f"tonality case {case_id} requires phrase_boundaries")
        if any(
            not isinstance(value, (int, float)) or value < 0
            for value in case["phrase_boundaries"]
        ) or case["phrase_boundaries"] != sorted(case["phrase_boundaries"]):
            raise ValueError(f"tonality case {case_id} has invalid phrase_boundaries")
        if not isinstance(case["local_tonality"], str) or " " not in case["local_tonality"]:
            raise ValueError(f"tonality case {case_id} has invalid local_tonality")
        if not isinstance(case["notation_key_signature"], str):
            raise ValueError(f"tonality case {case_id} has invalid notation_key_signature")
        if not isinstance(case["cadence_type"], str) or not isinstance(
            case["tonicization_or_modulation"], str
        ):
            raise ValueError(f"tonality case {case_id} has invalid evidence labels")
        normalized.append(case)
    return normalized


def score_predictions(
    cases: list[dict[str, object]],
    predictions: dict[str, dict[str, object]],
    *,
    asset_root: Path,
) -> dict[str, object]:
    cases = validate_manifest({"cases": cases}, asset_root=asset_root)
    if {case["id"] for case in cases} != set(predictions):
        raise ValueError("tonality predictions do not match manifest cases")
    top1 = top2 = eligible = wrong_notation = 0
    calibration_errors = []
    for case in cases:
        prediction = predictions[case["id"]]
        truth = case["local_tonality"]
        candidates = prediction.get("candidates", [])
        if not isinstance(candidates, list) or len(candidates) > 2:
            raise ValueError(f"prediction {case['id']} must contain at most two candidates")
        if any(not isinstance(item, dict) for item in candidates):
            raise ValueError(f"prediction {case['id']} candidates must be objects")
        if any(not isinstance(item.get("value"), str) or not item["value"] for item in candidates):
            raise ValueError(f"prediction {case['id']} candidates require values")
        values = [item["value"] for item in candidates]
        if len(values) != len(set(values)):
            raise ValueError(f"prediction {case['id']} contains duplicate candidates")
        scores = [item.get("score") for item in candidates]
        if any(not isinstance(score, (int, float)) or not 0 <= score <= 1 for score in scores):
            raise ValueError(f"prediction {case['id']} contains invalid candidate score")
        if values and values[0] == truth:
            top1 += 1
        if truth in values[:2]:
            top2 += 1
        predicted_probability = float(
            next(
                (item.get("score", 0.0) for item in candidates if item.get("value") == truth),
                0.0,
            )
        )
        if candidates and abs(sum(scores) - 1.0) > 0.01:
            raise ValueError(f"prediction {case['id']} candidate scores must sum to one")
        calibration_errors.append((predicted_probability, values[0] == truth if values else False))
        if prediction.get("notation_eligible") is True:
            eligible += 1
            if prediction.get("notation_key_signature") != case["notation_key_signature"]:
                wrong_notation += 1
    total = len(cases)
    abstention_rate = (total - eligible) / total
    error_rate = wrong_notation / eligible if eligible else 1.0
    calibration_error = _expected_calibration_error(calibration_errors)
    return {
        "total": total,
        "top1_accuracy": top1 / total,
        "top2_recall": top2 / total,
        "candidate_calibration_error": calibration_error,
        "notation_eligible_count": eligible,
        "notation_error_rate": error_rate,
        "abstention_rate": abstention_rate,
        "passed": bool(eligible and error_rate <= 0.05),
    }


def _expected_calibration_error(samples: list[tuple[float, bool]], bins: int = 10) -> float:
    if not samples:
        return 0.0
    total = len(samples)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            sample
            for sample in samples
            if lower <= sample[0] < upper
            or (index == bins - 1 and sample[0] == 1)
        ]
        if bucket:
            confidence = mean(sample[0] for sample in bucket)
            accuracy = sum(sample[1] for sample in bucket) / len(bucket)
            error += len(bucket) / total * abs(confidence - accuracy)
    return round(error, 6)


def manifest_fingerprint(cases: list[dict[str, object]]) -> str:
    payload = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> tuple[list[dict[str, object]], str]:
    cases = validate_manifest(
        json.loads(path.read_text(encoding="utf-8")), asset_root=path.parent
    )
    return cases, manifest_fingerprint(cases)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    cases, fingerprint = load_manifest(args.manifest)
    print(json.dumps({"case_count": len(cases), "fingerprint": fingerprint}, ensure_ascii=False))
