"""Validate accepted artifacts against their frozen acceptance record, read-only."""

import argparse
import json
from pathlib import Path

from app.pipeline.score_io import read_musicxml_structure
from scripts.build_reviewed_candidates import ACCEPTANCE
from scripts.piano_comparison_cases import file_sha256


def keyed(rows):
    result = {row["case_id"]: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate candidate case")
    return result


def validate(root: Path, acceptance: Path = ACCEPTANCE):
    registry = json.loads(acceptance.read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    if (
        registry.get("production_eligible") is not False
        or manifest.get("production_eligible") is not False
    ):
        raise ValueError("candidate records cannot authorize production")
    if manifest["acceptance_sha256"] != file_sha256(acceptance):
        raise ValueError("acceptance record changed")
    if manifest["status"] != "accepted_candidates_frozen_not_production_release":
        raise ValueError("candidate build is not complete")
    if (
        manifest["acceptance_source"] != registry["confirmation_source"]
        or manifest["confirmation_text"] != registry["confirmation_text"]
    ):
        raise ValueError("confirmation attribution changed")
    expected = keyed(registry["cases"])
    actual = keyed(manifest["cases"])
    if set(expected) != set(actual):
        raise ValueError("candidate case set changed")
    results = []
    for case, reference in expected.items():
        current = actual[case]
        for field in ("status", "source_kind", "known_limitations"):
            if current[field] != reference[field]:
                raise ValueError(f"{case}: {field} changed")
        if set(current["files"]) != set(reference["files"]):
            raise ValueError(f"{case}: artifact set changed")
        for name, ref in reference["files"].items():
            artifact = current["files"][name]
            if artifact["path"] != f"{case}/{name}":
                raise ValueError("unexpected artifact path")
            path = (root / artifact["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("artifact escaped candidate directory")
            if artifact["sha256"] != ref["sha256"] or file_sha256(path) != ref["sha256"]:
                raise ValueError(f"{case}: artifact fingerprint mismatch")
        structure = read_musicxml_structure(root / case / "score.musicxml")
        if structure != current["structure"]:
            raise ValueError(f"{case}: parsed structure differs from manifest")
        results.append(
            {
                "case_id": case,
                "frozen_artifacts_verified": True,
                "known_limitations": reference["known_limitations"],
                "staff_count": structure["staff_count"],
                "measure_duration_errors": structure["measure_duration_error_count"],
            }
        )
    return {
        "candidate_integrity_passed": True,
        "production_eligible": False,
        "scope": "file identity and parser checks only; not model readiness or new human review",
        "manifest_sha256": file_sha256(root / "manifest.json"),
        "validator_sha256": file_sha256(Path(__file__)),
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = validate(args.directory)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        with args.report.open("x") as handle:
            handle.write(text)
    print(text)
