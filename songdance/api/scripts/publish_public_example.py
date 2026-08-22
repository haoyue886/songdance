import json
import shutil
import tempfile
from pathlib import Path

from app.pipeline.quality import pipeline_postprocess_version
from app.pipeline.score import (
    ORNAMENT_REVIEW_REQUIRED,
    read_musicxml_structure,
    read_musicxml_visible_metadata,
)
from app.pipeline.transcribe import MODEL_VERSION
from scripts.human_quality_gate import file_sha256
from scripts.public_example_activation import exchange_directories as _exchange_directories
from scripts.public_example_provenance import build_provenance as _build_provenance
from scripts.public_example_reference import validate_reference_contract
from scripts.public_example_review import (
    COMPLETED_REVIEW_RATINGS,
)
from scripts.public_example_review import (
    completed_review as _completed_review,
)
from scripts.public_example_review import (
    validate_notation_density as _validate_notation_density,
)
from scripts.score_parser_validation import validate_external_parsers

API_ROOT = Path(__file__).parents[1]
PROJECT_ROOT = API_ROOT.parent
FIXTURE_ROOT = API_ROOT / "tests/fixtures/audio"
PUBLIC_ROOT = PROJECT_ROOT / "web/public/examples/mozart-sonata"
CASE_ID = "03-mozart-sonata"
SOURCE_AUDIO = FIXTURE_ROOT / "human-generated" / f"{CASE_ID}.wav"
HUMAN_RATING_FILE = FIXTURE_ROOT / "human-review-phase13-baseline.json"
PUBLIC_REVIEW_FILE = FIXTURE_ROOT / "public-example-review.json"
REFERENCE_CONTRACT_FILE = FIXTURE_ROOT / "references/mozart-k545-movement1.json"
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
    review = _public_review(source_root)
    completed_review = _completed_review(review)
    timeline = _read_json(source_root / "timeline.json")
    reference_validation = _validate_source(
        source_root, source_metadata, timeline, completed_review
    )

    score_path = (source_root / "score.musicxml").resolve()
    external = validate_external_parsers([score_path])[str(score_path)]
    if any(parser["status"] != "passed" for parser in external.values()):
        raise RuntimeError("public example failed xmllint or OSMD validation")

    PUBLIC_ROOT.parent.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{PUBLIC_ROOT.name}-stage-", dir=PUBLIC_ROOT.parent)
    )
    try:
        shutil.copy2(SOURCE_AUDIO, stage_root / "source.wav")
        for filename in PUBLISHED_ARTIFACTS.values():
            shutil.copy2(source_root / filename, stage_root / filename)
        artifacts = {
            kind: {
                "sha256": file_sha256(stage_root / filename),
                "size_bytes": (stage_root / filename).stat().st_size,
            }
            for kind, filename in PUBLISHED_ARTIFACTS.items()
        }
        provenance = _build_provenance(
            PUBLIC_TITLE,
            PUBLIC_PERFORMER,
            source_metadata,
            timeline,
            review,
            completed_review,
            reference_validation,
            artifacts,
            external,
        )
        (stage_root / "provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _replace_public_directory(stage_root)
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
    return provenance


def reset_review_for_current_artifacts() -> dict[str, object]:
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    previous = _read_json(PUBLIC_REVIEW_FILE)
    latest_completed = _completed_review(previous)
    review = {
        "case_id": CASE_ID,
        "audio_sha256": file_sha256(SOURCE_AUDIO),
        "timeline_sha256": file_sha256(source_root / "timeline.json"),
        "model_version": MODEL_VERSION,
        "rating": "pending",
        "reviewed_at": None,
        "review_state": previous["review_state"],
        "review_resume_condition": previous["review_resume_condition"],
        "latest_completed_review": latest_completed,
        "notes": "",
    }
    PUBLIC_REVIEW_FILE.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return review


def _replace_public_directory(stage_root: Path) -> None:
    if not PUBLIC_ROOT.exists():
        stage_root.replace(PUBLIC_ROOT)
        return
    _exchange_directories(stage_root, PUBLIC_ROOT)
    shutil.rmtree(stage_root)


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
    reference_validation = validate_reference_contract(
        REFERENCE_CONTRACT_FILE,
        CASE_ID,
        SOURCE_AUDIO,
        source_metadata,
        timeline,
        PUBLIC_ROOT / "score.musicxml",
    )
    expected_metadata = {
        "title": PUBLIC_TITLE,
        "performer": PUBLIC_PERFORMER,
        "source_page": source_metadata["source_page"],
        "license": source_metadata["license"],
        "license_url": source_metadata["license_url"],
        "clip_start_sec": source_metadata["start_sec"],
        "clip_duration_sec": source_metadata["duration_seconds"],
        "audio_sha256": source_metadata["clip_sha256"],
        "review_state": review["review_state"],
        "review_resume_condition": review["review_resume_condition"],
        "latest_completed_review": _completed_review(review),
        "reference_validation": reference_validation,
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
    _validate_notation_density(structure)
    visible_metadata = _validate_visible_score_metadata(PUBLIC_ROOT / "score.musicxml")
    return {
        "provenance": provenance,
        "timeline": timeline,
        "structure": structure,
        "visible_metadata": visible_metadata,
    }


def _validate_visible_score_metadata(score_path: Path) -> dict[str, object]:
    visible_metadata = read_musicxml_visible_metadata(score_path)
    visible_titles = [
        title
        for title in (
            visible_metadata["work_title"],
            visible_metadata["movement_title"],
        )
        if title
    ]
    if visible_titles != [CASE_ID]:
        raise ValueError("public example score must contain exactly one current title")
    if any("music21" in composer.casefold() for composer in visible_metadata["composers"]):
        raise ValueError("public example exposes the internal score engine as composer")
    return visible_metadata


def _validate_source(
    source_root: Path,
    source_metadata: dict[str, object],
    timeline: dict[str, object],
    completed_review: dict[str, str],
) -> dict[str, object]:
    if file_sha256(SOURCE_AUDIO) != source_metadata["clip_sha256"]:
        raise ValueError("source audio does not match the fixed regression clip")
    if completed_review["rating"] not in COMPLETED_REVIEW_RATINGS:
        raise ValueError("public example has no completed human review history")
    if any(
        flag in timeline["quality_flags"]
        for flag in {
            "TIME_SIGNATURE_DEFAULTED_4_4",
            "TIME_SIGNATURE_ASSUMED_4_4",
            "STAFF_DISTRIBUTION_SUSPECT",
            ORNAMENT_REVIEW_REQUIRED,
        }
    ):
        raise ValueError("public example source has a blocking quality flag")
    distribution = timeline.get("reconstruction", {}).get("staff_distribution", {})
    if distribution.get("status") != "passed":
        raise ValueError("public example source must pass staff distribution validation")
    reference_validation = validate_reference_contract(
        REFERENCE_CONTRACT_FILE,
        CASE_ID,
        SOURCE_AUDIO,
        source_metadata,
        timeline,
        source_root / "score.musicxml",
    )
    expected_version = pipeline_postprocess_version(timeline["cleanup"], timeline["analysis"])
    if timeline["model_version"] != MODEL_VERSION:
        raise ValueError("source artifact model version is stale")
    if timeline["postprocess_version"] != expected_version:
        raise ValueError("source artifact postprocess version is stale")
    structure = read_musicxml_structure(source_root / "score.musicxml")
    if structure["errors"]:
        raise ValueError("source MusicXML has structure errors")
    _validate_notation_density(structure)
    _validate_visible_score_metadata(source_root / "score.musicxml")
    return reference_validation


def _source_metadata() -> dict[str, object]:
    cases = _read_json(FIXTURE_ROOT / "human-provenance.json")["cases"]
    return next(case for case in cases if case["id"] == CASE_ID)


def _public_review(source_root: Path) -> dict[str, object]:
    review = _read_json(PUBLIC_REVIEW_FILE)
    expected = {
        "case_id": CASE_ID,
        "audio_sha256": file_sha256(SOURCE_AUDIO),
        "timeline_sha256": file_sha256(source_root / "timeline.json"),
        "model_version": MODEL_VERSION,
    }
    if any(review.get(key) != value for key, value in expected.items()):
        raise ValueError("public example review does not match the publishing source")
    rating = review.get("rating")
    reviewed_at = review.get("reviewed_at")
    if rating == "pending" and reviewed_at is not None:
        raise ValueError("pending public example review must not have a review timestamp")
    if rating in COMPLETED_REVIEW_RATINGS and not reviewed_at:
        raise ValueError("completed public example review requires a review timestamp")
    if rating not in {"pending", *COMPLETED_REVIEW_RATINGS}:
        raise ValueError("invalid public example review rating")
    review_state = review.get("review_state")
    resume_condition = review.get("review_resume_condition")
    if review_state not in {"active", "review_paused"}:
        raise ValueError("invalid public example review state")
    if review_state == "review_paused" and resume_condition != (
        "reference_aligned_transcription_ready"
    ):
        raise ValueError("paused public example review requires a recovery condition")
    if review_state == "active" and resume_condition is not None:
        raise ValueError("active public example review cannot have a recovery condition")
    if rating == "pending":
        _completed_review(review)
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
