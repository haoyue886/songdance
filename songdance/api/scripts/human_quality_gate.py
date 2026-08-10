import hashlib
import json
from pathlib import Path

from app.pipeline.quality import pipeline_postprocess_version
from app.pipeline.transcribe import FRAME_THRESHOLD, MODEL_VERSION, ONSET_THRESHOLD

ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/audio"
PIPELINE_ROOT = ROOT / "app/pipeline"
MANIFEST_PATH = FIXTURE_ROOT / "human-manifest.json"
PROVENANCE_PATH = FIXTURE_ROOT / "human-provenance.json"
REVIEW_PATH = FIXTURE_ROOT / "human-review.json"
ARTIFACT_FILENAMES = {
    "raw_midi": "raw.mid",
    "midi": "score.mid",
    "musicxml": "score.musicxml",
    "timeline": "timeline.json",
}
PIPELINE_FILES = (
    "audio.py",
    "transcribe.py",
    "cleanup.py",
    "analysis.py",
    "analysis_features.py",
    "analysis_runtime.py",
    "harmony.py",
    "quantize.py",
    "score.py",
    "score_validation.py",
    "voicing.py",
    "artifacts.py",
)
RATING_DEFINITION = {
    "direct_use": "可直接使用",
    "minor_edits": "30 秒内不超过 10 个明显错音或漏音，且无需整体重建节拍网格",
    "needs_redo": "需要重做",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_suite_fingerprint(
    fixture_root: Path = FIXTURE_ROOT,
    pipeline_root: Path = PIPELINE_ROOT,
) -> str:
    manifest = _read_json(fixture_root / "human-manifest.json")
    provenance = _read_json(fixture_root / "human-provenance.json")
    provenance_by_id = {case["id"]: case for case in provenance["cases"]}
    cases = []
    for case in manifest["cases"]:
        case_id = case["id"]
        source_sha = file_sha256(fixture_root / "human-generated" / f"{case_id}.wav")
        if source_sha != provenance_by_id[case_id]["clip_sha256"]:
            raise ValueError(f"source fingerprint mismatch for {case_id}")
        artifact_root = fixture_root / "human-review-artifacts" / case_id
        cases.append(
            {
                "id": case_id,
                "source_sha256": source_sha,
                "artifacts": {
                    kind: file_sha256(artifact_root / filename)
                    for kind, filename in ARTIFACT_FILENAMES.items()
                },
            }
        )
    payload = {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "thresholds": {"onset": ONSET_THRESHOLD, "frame": FRAME_THRESHOLD},
        "postprocess_version": pipeline_postprocess_version(),
        "pipeline_sha256": {
            filename: file_sha256(pipeline_root / filename) for filename in PIPELINE_FILES
        },
        "cases": cases,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def reset_review(manifest: dict, review_path: Path = REVIEW_PATH) -> None:
    review = {
        "schema_version": 2,
        "model_version": MODEL_VERSION,
        "suite_fingerprint": None,
        "reviewer": {"midi_daw_experience": None, "reviewed_at": None},
        "rating_definition": RATING_DEFINITION,
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


def record_raw_midi_note_counts(
    note_counts: dict[str, int], review_path: Path = REVIEW_PATH
) -> None:
    review = _read_json(review_path)
    expected_ids = {result["id"] for result in review["results"]}
    if set(note_counts) != expected_ids:
        raise ValueError("raw MIDI note counts do not match the fixed manifest")
    for result in review["results"]:
        result["raw_midi_note_count"] = note_counts[result["id"]]
    _write_json(review_path, review)


def bind_generated_suite(
    review_path: Path = REVIEW_PATH,
    fixture_root: Path = FIXTURE_ROOT,
    pipeline_root: Path = PIPELINE_ROOT,
) -> str:
    review = _read_json(review_path)
    if review["reviewer"]["midi_daw_experience"] is not None or any(
        case["rating"] != "pending" for case in review["results"]
    ):
        raise ValueError("generated suite must be pending human review")
    fingerprint = compute_suite_fingerprint(fixture_root, pipeline_root)
    review["suite_fingerprint"] = fingerprint
    _write_json(review_path, review)
    return fingerprint


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
