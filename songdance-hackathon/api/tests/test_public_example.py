import json
import shutil

import pytest

import scripts.publish_public_example as publisher
from scripts.human_quality_gate import file_sha256
from scripts.publish_public_example import (
    CASE_ID,
    FIXTURE_ROOT,
    HUMAN_RATING_FILE,
    PUBLIC_ROOT,
    PUBLISHED_ARTIFACTS,
    SOURCE_AUDIO,
    validate_published_example,
)


def test_public_example_matches_current_pipeline_and_provenance() -> None:
    result = validate_published_example()

    assert result["structure"]["chord_count"] > 0
    assert "HAND_ASSIGNMENT_MIDDLE_C" not in result["timeline"]["quality_flags"]
    assert "TIME_SIGNATURE_DEFAULTED_4_4" not in result["timeline"]["quality_flags"]
    assert "TIME_SIGNATURE_ASSUMED_4_4" not in result["timeline"]["quality_flags"]
    assert result["provenance"]["review_status"] in {
        "pending",
        "minor_edits",
        "direct_use",
    }
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    ratings = {
        item["id"]: item["rating"]
        for item in json.loads(HUMAN_RATING_FILE.read_text(encoding="utf-8"))["results"]
    }
    assert ratings[CASE_ID] in {"minor_edits", "direct_use"}
    assert file_sha256(PUBLIC_ROOT / "source.wav") == file_sha256(SOURCE_AUDIO)
    assert all(
        file_sha256(PUBLIC_ROOT / filename) == file_sha256(source_root / filename)
        for filename in PUBLISHED_ARTIFACTS.values()
    )


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("title", "Stale title"),
        ("performer", "Stale performer"),
        ("source_page", "https://example.invalid/source"),
        ("license", "Proprietary"),
        ("license_url", "https://example.invalid/license"),
        ("clip_start_sec", -1),
        ("clip_duration_sec", 1),
        ("audio_sha256", "0" * 64),
        ("midi_sha256", "0" * 64),
        ("musicxml_sha256", "0" * 64),
        ("timeline_sha256", "0" * 64),
        ("review_status", "minor_edits"),
    ],
)
def test_public_example_rejects_stale_provenance(
    tmp_path, monkeypatch: pytest.MonkeyPatch, field: str, stale_value: object
) -> None:
    public_root = tmp_path / "mozart-sonata"
    shutil.copytree(PUBLIC_ROOT, public_root)
    provenance_path = public_root / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance[field] = stale_value
    provenance_path.write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)

    with pytest.raises(ValueError):
        publisher.validate_published_example()


def test_public_example_review_is_bound_to_current_artifacts(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review_path = tmp_path / "public-example-review.json"
    review = json.loads(publisher.PUBLIC_REVIEW_FILE.read_text(encoding="utf-8"))
    review["timeline_sha256"] = "0" * 64
    review_path.write_text(json.dumps(review), encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_REVIEW_FILE", review_path)

    with pytest.raises(ValueError, match="does not match the publishing source"):
        publisher.validate_published_example()
