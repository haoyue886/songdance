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
    assert result["provenance"]["latest_completed_review"] == {
        "rating": "minor_edits",
        "reviewed_at": "2026-08-06T10:24:43.117449+00:00",
        "model_version": "basic-pitch-0.4.0/icassp-2022-onnx/o0.5-f0.3",
    }
    assert result["visible_metadata"] == {
        "work_title": None,
        "movement_title": CASE_ID,
        "composers": [],
        "software": ["music21 v.10.5.0"],
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
        ("latest_completed_review", {"rating": "needs_redo"}),
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


def test_failed_parser_validation_does_not_overwrite_public_example(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root = tmp_path / "mozart-sonata"
    public_root.mkdir()
    sentinel = public_root / "timeline.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)
    monkeypatch.setattr(
        publisher,
        "validate_external_parsers",
        lambda paths: {
            str(paths[0]): {
                "xmllint": {"status": "passed"},
                "osmd": {"status": "failed"},
            }
        },
    )

    with pytest.raises(RuntimeError, match="failed xmllint or OSMD validation"):
        publisher.publish()

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(public_root.iterdir()) == [sentinel]


@pytest.mark.parametrize(
    ("visible_metadata", "error"),
    [
        (
            {
                "work_title": "Duplicate stale title",
                "movement_title": CASE_ID,
                "composers": [],
                "software": ["music21 v.10.5.0"],
            },
            "exactly one current title",
        ),
        (
            {
                "work_title": None,
                "movement_title": CASE_ID,
                "composers": ["Music21 v.10.5.0"],
                "software": ["music21 v.10.5.0"],
            },
            "internal score engine",
        ),
    ],
)
def test_invalid_visible_metadata_does_not_overwrite_public_example(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    visible_metadata: dict[str, object],
    error: str,
) -> None:
    public_root = tmp_path / "mozart-sonata"
    public_root.mkdir()
    sentinel = public_root / "timeline.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)
    monkeypatch.setattr(
        publisher,
        "read_musicxml_visible_metadata",
        lambda _path: visible_metadata,
    )

    with pytest.raises(ValueError, match=error):
        publisher.publish()

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(public_root.iterdir()) == [sentinel]


def test_copy_failure_does_not_overwrite_public_example(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root = tmp_path / "mozart-sonata"
    public_root.mkdir()
    sentinel = public_root / "timeline.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)
    monkeypatch.setattr(
        publisher,
        "validate_external_parsers",
        lambda paths: {
            str(paths[0]): {
                "xmllint": {"status": "passed"},
                "osmd": {"status": "passed"},
            }
        },
    )
    original_copy = publisher.shutil.copy2
    copy_count = 0

    def fail_second_copy(source, destination):
        nonlocal copy_count
        copy_count += 1
        if copy_count == 2:
            raise OSError("copy interrupted")
        return original_copy(source, destination)

    monkeypatch.setattr(publisher.shutil, "copy2", fail_second_copy)

    with pytest.raises(OSError, match="copy interrupted"):
        publisher.publish()

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(public_root.iterdir()) == [sentinel]


def test_provenance_failure_does_not_overwrite_public_example(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root = tmp_path / "mozart-sonata"
    public_root.mkdir()
    sentinel = public_root / "timeline.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)
    _allow_external_parsers(monkeypatch)
    original_write_text = publisher.Path.write_text

    def fail_staged_provenance(path, *args, **kwargs):
        if path.name == "provenance.json" and "-stage-" in path.parent.name:
            raise OSError("provenance interrupted")
        return original_write_text(path, *args, **kwargs)

    monkeypatch.setattr(publisher.Path, "write_text", fail_staged_provenance)

    with pytest.raises(OSError, match="provenance interrupted"):
        publisher.publish()

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(public_root.iterdir()) == [sentinel]


def test_activation_failure_restores_previous_public_example(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root = tmp_path / "mozart-sonata"
    public_root.mkdir()
    sentinel = public_root / "timeline.json"
    sentinel.write_text("unchanged", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)
    _allow_external_parsers(monkeypatch)
    monkeypatch.setattr(
        publisher,
        "_exchange_directories",
        lambda _stage, _public: (_ for _ in ()).throw(OSError("activation interrupted")),
    )

    with pytest.raises(OSError, match="activation interrupted"):
        publisher.publish()

    assert sentinel.read_text(encoding="utf-8") == "unchanged"
    assert list(public_root.iterdir()) == [sentinel]


def test_public_directory_activation_uses_atomic_exchange(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    public_root = tmp_path / "public"
    public_root.mkdir()
    (public_root / "version.txt").write_text("old", encoding="utf-8")
    stage_root = tmp_path / "stage"
    stage_root.mkdir()
    (stage_root / "version.txt").write_text("new", encoding="utf-8")
    monkeypatch.setattr(publisher, "PUBLIC_ROOT", public_root)

    publisher._replace_public_directory(stage_root)

    assert (public_root / "version.txt").read_text(encoding="utf-8") == "new"
    assert not stage_root.exists()


def _allow_external_parsers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publisher,
        "validate_external_parsers",
        lambda paths: {
            str(paths[0]): {
                "xmllint": {"status": "passed"},
                "osmd": {"status": "passed"},
            }
        },
    )
