import hashlib
import json
from pathlib import Path

from app.pipeline.quality import pipeline_postprocess_version
from app.pipeline.transcribe import MODEL_VERSION
from scripts.human_quality_gate import ARTIFACT_FILENAMES, PIPELINE_FILES, file_sha256

ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/audio"
PIPELINE_ROOT = ROOT / "app/pipeline"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
REVIEW_PATH = FIXTURE_ROOT / "structure-review.json"
ARTIFACT_ROOT = FIXTURE_ROOT / "structure-review-artifacts"
GENERATED_ROOT = FIXTURE_ROOT / "generated"


def compute_structure_suite_fingerprint(
    fixture_root: Path = FIXTURE_ROOT,
    pipeline_root: Path = PIPELINE_ROOT,
) -> str:
    manifest = _read_json(fixture_root / "manifest.json")
    cases = []
    for case in manifest["cases"]:
        case_id = case["id"]
        artifact_root = fixture_root / "structure-review-artifacts" / case_id
        cases.append(
            {
                "id": case_id,
                "audio_sha256": file_sha256(fixture_root / "generated" / f"{case_id}.wav"),
                "truth_sha256": file_sha256(fixture_root / "generated" / f"{case_id}.mid"),
                "artifacts": {
                    kind: file_sha256(artifact_root / filename)
                    for kind, filename in ARTIFACT_FILENAMES.items()
                },
            }
        )
    payload = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "postprocess_version": pipeline_postprocess_version(),
        "pipeline_sha256": {
            filename: file_sha256(pipeline_root / filename) for filename in PIPELINE_FILES
        },
        "manifest": manifest,
        "cases": cases,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def reset_structure_review(manifest: dict, review_path: Path = REVIEW_PATH) -> None:
    review = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "suite_fingerprint": None,
        "reviewer": {"midi_daw_experience": None, "reviewed_at": None},
        "minimum_readable_count": 13,
        "results": [
            {
                "id": case["id"],
                "raw_midi_note_count": None,
                "rating": "pending",
                "notes": "",
            }
            for case in manifest["cases"]
        ],
    }
    _write_json(review_path, review)


def bind_structure_suite(
    note_counts: dict[str, int],
    parser_validation: dict[str, dict[str, object]],
    review_path: Path = REVIEW_PATH,
    fixture_root: Path = FIXTURE_ROOT,
) -> str:
    review = _read_json(review_path)
    for result in review["results"]:
        result["raw_midi_note_count"] = note_counts[result["id"]]
        result["parser_validation"] = parser_validation[result["id"]]
    review["suite_fingerprint"] = compute_structure_suite_fingerprint(fixture_root)
    _write_json(review_path, review)
    return review["suite_fingerprint"]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
