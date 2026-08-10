import json
from pathlib import Path

from app.pipeline.transcribe import MODEL_VERSION
from scripts.human_quality_gate import compute_suite_fingerprint

ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/audio"
MANIFEST_PATH = FIXTURE_ROOT / "human-manifest.json"
REVIEW_PATH = FIXTURE_ROOT / "human-review.json"
RATINGS = {"direct_use", "minor_edits", "needs_redo"}


def validate(
    review_path: Path = REVIEW_PATH,
    fixture_root: Path = FIXTURE_ROOT,
) -> dict:
    manifest = json.loads((fixture_root / "human-manifest.json").read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review["model_version"] != MODEL_VERSION:
        raise ValueError("human review uses a different model version")
    if review.get("suite_fingerprint") != compute_suite_fingerprint(fixture_root):
        raise ValueError("human review suite fingerprint is stale")
    if review["reviewer"]["midi_daw_experience"] is not True:
        raise ValueError("reviewer must confirm MIDI/DAW experience")
    if not review["reviewer"]["reviewed_at"]:
        raise ValueError("reviewed_at is required")
    expected_ids = [case["id"] for case in manifest["cases"]]
    actual_ids = [case["id"] for case in review["results"]]
    if actual_ids != expected_ids:
        raise ValueError("human review cases do not match the fixed manifest")
    if any(
        type(case.get("raw_midi_note_count")) is not int
        or case["raw_midi_note_count"] <= 0
        for case in review["results"]
    ):
        raise ValueError("human review is missing raw MIDI note counts")
    if any(case["rating"] not in RATINGS for case in review["results"]):
        raise ValueError("all cases need one of the three allowed ratings")
    usable = sum(case["rating"] != "needs_redo" for case in review["results"])
    outcome = {"usable_count": usable, "total_count": len(actual_ids), "passed": usable >= 7}
    print(json.dumps(outcome, ensure_ascii=False))
    return outcome


if __name__ == "__main__":
    result = validate()
    raise SystemExit(0 if result["passed"] else 1)
