import hashlib
import json
from pathlib import Path

import pytest

from scripts import human_review_server, run_human_regression
from scripts.human_quality_gate import (
    ARTIFACT_FILENAMES,
    bind_generated_suite,
    compute_suite_fingerprint,
    reset_review,
)
from scripts.validate_human_review import validate


def test_human_review_uses_local_piano_samples() -> None:
    assert "createOscillator" not in human_review_server.HTML
    assert "decodeAudioData" in human_review_server.HTML
    assert len(list(human_review_server.PIANO_ASSET_ROOT.glob("*.mp3"))) == 30


def test_real_piano_human_gate_has_fixed_licensed_sources() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    manifest = json.loads((fixture_root / "human-manifest.json").read_text(encoding="utf-8"))
    provenance = json.loads((fixture_root / "human-provenance.json").read_text(encoding="utf-8"))
    review = json.loads((fixture_root / "human-review.json").read_text(encoding="utf-8"))
    allowed = set(manifest["authorization"]["allowed_licenses"])
    expected_ids = [item["id"] for item in manifest["cases"]]

    assert manifest["suite_type"] == "real_piano_human_quality_gate"
    assert manifest["product_quality_gate"] is True
    assert manifest["duration_seconds"] == 30
    assert len(expected_ids) == 10
    assert [item["id"] for item in provenance["cases"]] == expected_ids
    assert [item["id"] for item in review["results"]] == expected_ids
    assert all(item["license"] in allowed for item in provenance["cases"])
    assert all(item["duration_seconds"] == 30 for item in provenance["cases"])
    assert all(len(item["clip_sha256"]) == 64 for item in provenance["cases"])
    assert review["suite_fingerprint"] == compute_suite_fingerprint(fixture_root)
    ratings = [item["rating"] for item in review["results"]]
    if "pending" in ratings:
        assert set(ratings) == {"pending"}
        assert review["reviewer"] == {"midi_daw_experience": None, "reviewed_at": None}
    else:
        assert set(ratings) <= {"direct_use", "minor_edits", "needs_redo"}
        assert review["reviewer"]["midi_daw_experience"] is True
        assert review["reviewer"]["reviewed_at"]
        usable = sum(rating != "needs_redo" for rating in ratings)
        outcome = validate(fixture_root / "human-review.json", fixture_root)
        assert outcome == {
            "usable_count": usable,
            "total_count": len(ratings),
            "passed": usable >= 7,
        }


def test_human_review_requires_experience_and_complete_ratings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review_path = tmp_path / "human-review.json"
    review_path.write_text(
        human_review_server.REVIEW_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(human_review_server, "REVIEW_PATH", review_path)
    initial_review = json.loads(review_path.read_text(encoding="utf-8"))
    for index, result in enumerate(initial_review["results"], start=1):
        result["raw_midi_note_count"] = index
    initial_review["results"][0].pop("raw_midi_note_count")
    initial_review["results"][1]["raw_midi_note_count"] = True
    review_path.write_text(json.dumps(initial_review), encoding="utf-8")
    manifest = json.loads(human_review_server.MANIFEST_PATH.read_text(encoding="utf-8"))
    results = [
        {"id": case["id"], "rating": "direct_use", "notes": "verified"}
        for case in manifest["cases"]
    ]

    with pytest.raises(ValueError, match="MIDI/DAW"):
        human_review_server.save_review({"midi_daw_experience": False, "results": results})
    results[-1]["rating"] = "pending"
    with pytest.raises(ValueError, match="全部 10 段"):
        human_review_server.save_review({"midi_daw_experience": True, "results": results})

    results[-1]["rating"] = "needs_redo"
    outcome = human_review_server.save_review({"midi_daw_experience": True, "results": results})
    assert outcome == {"usable_count": 9, "total_count": 10, "passed": True}
    saved = json.loads(review_path.read_text(encoding="utf-8"))
    assert saved["results"][0]["raw_midi_note_count"] == human_review_server._raw_midi_note_count(
        manifest["cases"][0]["id"]
    )
    assert saved["results"][1]["raw_midi_note_count"] == human_review_server._raw_midi_note_count(
        manifest["cases"][1]["id"]
    )
    assert [item["raw_midi_note_count"] for item in saved["results"][2:]] == list(range(3, 11))


@pytest.mark.parametrize("invalid_count", [None, -1, "275"])
def test_human_review_recovers_each_invalid_note_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid_count: object
) -> None:
    review_path = tmp_path / "human-review.json"
    review = json.loads(human_review_server.REVIEW_PATH.read_text(encoding="utf-8"))
    review["results"][0]["raw_midi_note_count"] = invalid_count
    review_path.write_text(json.dumps(review), encoding="utf-8")
    monkeypatch.setattr(human_review_server, "REVIEW_PATH", review_path)
    manifest = json.loads(human_review_server.MANIFEST_PATH.read_text(encoding="utf-8"))
    results = [
        {"id": case["id"], "rating": "direct_use", "notes": "verified"}
        for case in manifest["cases"]
    ]

    human_review_server.save_review({"midi_daw_experience": True, "results": results})

    saved = json.loads(review_path.read_text(encoding="utf-8"))
    assert saved["results"][0]["raw_midi_note_count"] == human_review_server._raw_midi_note_count(
        manifest["cases"][0]["id"]
    )


def test_regeneration_invalidates_existing_human_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture_root = tmp_path / "audio"
    output_dir = fixture_root / "human-generated"
    review_dir = fixture_root / "human-review-artifacts"
    output_dir.mkdir(parents=True)
    review_dir.mkdir()
    manifest = {"cases": [{"id": "case-1"}]}
    (fixture_root / "human-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (output_dir / "case-1.wav").write_bytes(b"source")
    review_path = fixture_root / "human-review.json"
    review_path.write_text(
        json.dumps(
            {
                "reviewer": {"midi_daw_experience": True, "reviewed_at": "old"},
                "results": [{"id": "case-1", "rating": "direct_use", "notes": "old"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(run_human_regression, "FIXTURE_ROOT", fixture_root)
    monkeypatch.setattr(run_human_regression, "OUTPUT_DIR", output_dir)
    monkeypatch.setattr(run_human_regression, "REVIEW_DIR", review_dir)
    monkeypatch.setattr(run_human_regression, "REVIEW_PATH", review_path)

    def stop_after_reset(*_args, **_kwargs) -> None:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        assert review["reviewer"]["midi_daw_experience"] is None
        assert review["results"][0]["rating"] == "pending"
        raise RuntimeError("stop after reset")

    monkeypatch.setattr(run_human_regression, "preprocess_audio", stop_after_reset)
    with pytest.raises(RuntimeError, match="stop after reset"):
        run_human_regression.run()


def test_validator_rejects_artifact_changed_after_human_review(tmp_path: Path) -> None:
    fixture_root = tmp_path / "audio"
    generated = fixture_root / "human-generated"
    artifacts = fixture_root / "human-review-artifacts"
    generated.mkdir(parents=True)
    cases = [{"id": f"case-{index}"} for index in range(10)]
    (fixture_root / "human-manifest.json").write_text(
        json.dumps({"cases": cases}), encoding="utf-8"
    )
    provenance = []
    for case in cases:
        case_id = case["id"]
        source = generated / f"{case_id}.wav"
        source.write_bytes(case_id.encode())
        provenance.append(
            {"id": case_id, "clip_sha256": hashlib.sha256(case_id.encode()).hexdigest()}
        )
        case_dir = artifacts / case_id
        case_dir.mkdir(parents=True)
        for filename in ARTIFACT_FILENAMES.values():
            (case_dir / filename).write_bytes(f"{case_id}:{filename}".encode())
    (fixture_root / "human-provenance.json").write_text(
        json.dumps({"cases": provenance}), encoding="utf-8"
    )
    review_path = fixture_root / "human-review.json"
    reset_review({"cases": cases}, review_path)
    bind_generated_suite(review_path, fixture_root)
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review["reviewer"] = {"midi_daw_experience": True, "reviewed_at": "2026-01-01T00:00:00Z"}
    for result in review["results"]:
        result["rating"] = "direct_use"
        result["raw_midi_note_count"] = 1
    review_path.write_text(json.dumps(review), encoding="utf-8")

    assert validate(review_path, fixture_root)["passed"] is True
    for invalid_count in (None, True, -1, "1"):
        review["results"][0]["raw_midi_note_count"] = invalid_count
        review_path.write_text(json.dumps(review), encoding="utf-8")
        with pytest.raises(ValueError, match="missing raw MIDI note counts"):
            validate(review_path, fixture_root)
    (artifacts / "case-1" / "score.mid").write_bytes(b"changed")
    with pytest.raises(ValueError, match="fingerprint is stale"):
        validate(review_path, fixture_root)
