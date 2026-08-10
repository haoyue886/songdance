import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.pipeline.quality import pipeline_postprocess_version
from app.pipeline.score import read_musicxml_structure
from app.pipeline.transcribe import MODEL_VERSION
from scripts.human_quality_gate import file_sha256
from scripts.score_parser_validation import validate_external_parsers

API_ROOT = Path(__file__).parents[1]
PROJECT_ROOT = API_ROOT.parent
FIXTURE_ROOT = API_ROOT / "tests/fixtures/audio"
PUBLIC_ROOT = PROJECT_ROOT / "web/public/examples/mozart-sonata"
CASE_ID = "03-mozart-sonata"
SOURCE_AUDIO = FIXTURE_ROOT / "human-generated" / f"{CASE_ID}.wav"
HUMAN_RATING_FILE = FIXTURE_ROOT / "human-review-phase13-baseline.json"
PUBLIC_REVIEW_FILE = FIXTURE_ROOT / "public-example-review.json"
PUBLIC_TITLE = "W.A. Mozart Sonata in C major"
PUBLIC_PERFORMER = "Varvara Semenchuk"
PUBLISHED_ARTIFACTS = {
    "midi": "score.mid",
    "musicxml": "score.musicxml",
    "timeline": "timeline.json",
}


def publish() -> dict[str, object]:
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    source_metadata = _source_metadata()
    timeline = _read_json(source_root / "timeline.json")
    _validate_source(source_root, source_metadata, timeline)
    review = _public_review(source_root)

    PUBLIC_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_AUDIO, PUBLIC_ROOT / "source.wav")
    for filename in PUBLISHED_ARTIFACTS.values():
        shutil.copy2(source_root / filename, PUBLIC_ROOT / filename)

    external = validate_external_parsers([PUBLIC_ROOT / "score.musicxml"])["score.musicxml"]
    if any(parser["status"] != "passed" for parser in external.values()):
        raise RuntimeError("public example failed xmllint or OSMD validation")

    artifacts = {
        kind: {
            "sha256": file_sha256(PUBLIC_ROOT / filename),
            "size_bytes": (PUBLIC_ROOT / filename).stat().st_size,
        }
        for kind, filename in PUBLISHED_ARTIFACTS.items()
    }
    provenance = {
        "title": PUBLIC_TITLE,
        "performer": PUBLIC_PERFORMER,
        "source_page": source_metadata["source_page"],
        "license": source_metadata["license"],
        "license_url": source_metadata["license_url"],
        "clip_start_sec": source_metadata["start_sec"],
        "clip_duration_sec": source_metadata["duration_seconds"],
        "audio_sha256": source_metadata["clip_sha256"],
        "model_version": timeline["model_version"],
        "postprocess_version": timeline["postprocess_version"],
        "review_status": review["rating"],
        "generated_at": datetime.now(UTC).isoformat(),
        "midi_sha256": artifacts["midi"]["sha256"],
        "musicxml_sha256": artifacts["musicxml"]["sha256"],
        "timeline_sha256": artifacts["timeline"]["sha256"],
        "artifacts": artifacts,
        "parser_validation": {"music21": {"status": "passed"}, **external},
    }
    (PUBLIC_ROOT / "provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return provenance


def validate_published_example() -> dict[str, object]:
    provenance = _read_json(PUBLIC_ROOT / "provenance.json")
    timeline = _read_json(PUBLIC_ROOT / "timeline.json")
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    expected_version = pipeline_postprocess_version(timeline["cleanup"], timeline["analysis"])
    if timeline["model_version"] != MODEL_VERSION:
        raise ValueError("public example model version is stale")
    if timeline["postprocess_version"] != expected_version:
        raise ValueError("public example postprocess version is stale")
    if provenance.get("postprocess_version") != expected_version:
        raise ValueError("public example provenance version is stale")
    source_metadata = _source_metadata()
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    review = _public_review(source_root)
    expected_metadata = {
        "title": PUBLIC_TITLE,
        "performer": PUBLIC_PERFORMER,
        "source_page": source_metadata["source_page"],
        "license": source_metadata["license"],
        "license_url": source_metadata["license_url"],
        "clip_start_sec": source_metadata["start_sec"],
        "clip_duration_sec": source_metadata["duration_seconds"],
        "audio_sha256": source_metadata["clip_sha256"],
    }
    if any(provenance.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("public example source metadata is stale")
    if provenance.get("review_status") != review["rating"]:
        raise ValueError("public example review status is stale")
    if file_sha256(PUBLIC_ROOT / "source.wav") != provenance.get("audio_sha256"):
        raise ValueError("public example audio fingerprint mismatch")
    if file_sha256(PUBLIC_ROOT / "source.wav") != file_sha256(SOURCE_AUDIO):
        raise ValueError("public example audio is stale against its publishing source")
    for kind, filename in PUBLISHED_ARTIFACTS.items():
        artifact = provenance.get("artifacts", {}).get(kind, {})
        path = PUBLIC_ROOT / filename
        if file_sha256(path) != file_sha256(source_root / filename):
            raise ValueError(f"public example {kind} is stale against its publishing source")
        if artifact.get("sha256") != file_sha256(path):
            raise ValueError(f"public example {kind} fingerprint mismatch")
        if provenance.get(f"{kind}_sha256") != file_sha256(path):
            raise ValueError(f"public example top-level {kind} fingerprint mismatch")
        if artifact.get("size_bytes") != path.stat().st_size:
            raise ValueError(f"public example {kind} size mismatch")
    structure = read_musicxml_structure(PUBLIC_ROOT / "score.musicxml")
    if structure["errors"]:
        raise ValueError("public example MusicXML has structure errors")
    return {"provenance": provenance, "timeline": timeline, "structure": structure}


def _validate_source(
    source_root: Path,
    source_metadata: dict[str, object],
    timeline: dict[str, object],
) -> None:
    if file_sha256(SOURCE_AUDIO) != source_metadata["clip_sha256"]:
        raise ValueError("source audio does not match the fixed regression clip")
    ratings = _read_json(HUMAN_RATING_FILE)["results"]
    rating = next(item["rating"] for item in ratings if item["id"] == CASE_ID)
    if rating not in {"minor_edits", "direct_use"}:
        raise ValueError("public example source has not passed the human quality gate")
    if any(
        flag in timeline["quality_flags"]
        for flag in {"TIME_SIGNATURE_DEFAULTED_4_4", "TIME_SIGNATURE_ASSUMED_4_4"}
    ):
        raise ValueError("public example source uses a default time signature")
    expected_version = pipeline_postprocess_version(timeline["cleanup"], timeline["analysis"])
    if timeline["model_version"] != MODEL_VERSION:
        raise ValueError("source artifact model version is stale")
    if timeline["postprocess_version"] != expected_version:
        raise ValueError("source artifact postprocess version is stale")
    structure = read_musicxml_structure(source_root / "score.musicxml")
    if structure["errors"]:
        raise ValueError("source MusicXML has structure errors")


def _source_metadata() -> dict[str, object]:
    cases = _read_json(FIXTURE_ROOT / "human-provenance.json")["cases"]
    return next(case for case in cases if case["id"] == CASE_ID)


def _public_review(source_root: Path) -> dict[str, object]:
    review = _read_json(PUBLIC_REVIEW_FILE)
    expected = {
        "case_id": CASE_ID,
        "audio_sha256": file_sha256(SOURCE_AUDIO),
        "timeline_sha256": file_sha256(source_root / "timeline.json"),
    }
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("public example review does not match the publishing source")
    rating = review.get("rating")
    reviewed_at = review.get("reviewed_at")
    if rating == "pending" and reviewed_at is not None:
        raise ValueError("pending public example review must not have a review timestamp")
    if rating in {"minor_edits", "direct_use"} and not reviewed_at:
        raise ValueError("approved public example review requires a review timestamp")
    if rating not in {"pending", "minor_edits", "direct_use"}:
        raise ValueError("invalid public example review rating")
    return review


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    result = publish()
    print(
        json.dumps(
            {
                "postprocess_version": result["postprocess_version"],
                "review_status": result["review_status"],
            },
            ensure_ascii=False,
        )
    )
