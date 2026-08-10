import json
from pathlib import Path

from app.pipeline.transcribe import MODEL_VERSION
from scripts.structure_quality_gate import (
    FIXTURE_ROOT,
    REVIEW_PATH,
    compute_structure_suite_fingerprint,
)

RATINGS = {"direct_use", "minor_edits", "needs_redo"}


def validate(
    review_path: Path = REVIEW_PATH, fixture_root: Path = FIXTURE_ROOT
) -> dict[str, object]:
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review["model_version"] != MODEL_VERSION:
        raise ValueError("structure review uses a different model version")
    if review.get("suite_fingerprint") != compute_structure_suite_fingerprint(
        fixture_root
    ):
        raise ValueError("structure review suite fingerprint is stale")
    if review["reviewer"]["midi_daw_experience"] is not True:
        raise ValueError("reviewer must confirm MIDI/DAW experience")
    if not review["reviewer"]["reviewed_at"]:
        raise ValueError("reviewed_at is required")
    expected = [case["id"] for case in manifest["cases"]]
    if [case["id"] for case in review["results"]] != expected:
        raise ValueError("structure review cases do not match the fixed manifest")
    if any(case["rating"] not in RATINGS for case in review["results"]):
        raise ValueError("all structure cases need a rating")
    if any(
        parser["status"] != "passed"
        for case in review["results"]
        for parser in case["parser_validation"].values()
    ):
        raise ValueError("structure review contains parser failures")
    usable = sum(case["rating"] != "needs_redo" for case in review["results"])
    outcome = {
        "usable_count": usable,
        "total_count": len(review["results"]),
        "minimum_readable_count": review["minimum_readable_count"],
        "passed": usable >= review["minimum_readable_count"],
    }
    print(json.dumps(outcome, ensure_ascii=False))
    return outcome


if __name__ == "__main__":
    result = validate()
    raise SystemExit(0 if result["passed"] else 1)
