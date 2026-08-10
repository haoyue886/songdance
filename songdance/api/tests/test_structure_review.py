import json
from pathlib import Path

import pytest

from scripts import structure_review_server, validate_structure_review
from scripts.structure_quality_gate import compute_structure_suite_fingerprint


def test_structure_review_suite_is_current_and_parser_clean() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    review = json.loads((fixture_root / "structure-review.json").read_text(encoding="utf-8"))

    assert len(manifest["cases"]) == 16
    assert review["suite_fingerprint"] == compute_structure_suite_fingerprint(
        fixture_root
    )
    assert [item["id"] for item in review["results"]] == [
        item["id"] for item in manifest["cases"]
    ]
    assert all(
        parser["status"] == "passed"
        for item in review["results"]
        for parser in item["parser_validation"].values()
    )
    ratings = {item["rating"] for item in review["results"]}
    if "pending" in ratings:
        assert ratings == {"pending"}
        assert review["reviewer"]["midi_daw_experience"] is None
    else:
        assert ratings <= {"direct_use", "minor_edits", "needs_redo"}


def test_structure_review_save_requires_all_cases_and_uses_13_of_16_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [{"id": f"case-{index:02d}"} for index in range(16)]
    manifest_path = tmp_path / "manifest.json"
    review_path = tmp_path / "structure-review.json"
    manifest_path.write_text(json.dumps({"cases": cases}), encoding="utf-8")
    review_path.write_text(
        json.dumps(
            {
                "suite_fingerprint": "current",
                "minimum_readable_count": 13,
                "reviewer": {"midi_daw_experience": None, "reviewed_at": None},
                "results": [
                    {
                        "id": case["id"],
                        "raw_midi_note_count": 1,
                        "parser_validation": {
                            "music21": {"status": "passed"},
                            "osmd": {"status": "passed"},
                            "xmllint": {"status": "passed"},
                        },
                        "rating": "pending",
                    }
                    for case in cases
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(structure_review_server, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(structure_review_server, "REVIEW_PATH", review_path)
    monkeypatch.setattr(
        structure_review_server,
        "compute_structure_suite_fingerprint",
        lambda: "current",
    )
    results = [
        {
            "id": case["id"],
            "rating": "direct_use" if index < 13 else "needs_redo",
            "notes": "checked",
        }
        for index, case in enumerate(cases)
    ]

    with pytest.raises(ValueError, match="全部 16 段"):
        structure_review_server.save_structure_review(
            {"midi_daw_experience": True, "results": results[:-1]}
        )
    outcome = structure_review_server.save_structure_review(
        {"midi_daw_experience": True, "results": results}
    )

    assert outcome == {"usable_count": 13, "total_count": 16, "passed": True}


def test_structure_review_validator_rejects_12_of_16(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = [{"id": f"case-{index:02d}"} for index in range(16)]
    fixture_root = tmp_path / "audio"
    fixture_root.mkdir()
    (fixture_root / "manifest.json").write_text(
        json.dumps({"cases": cases}), encoding="utf-8"
    )
    review_path = fixture_root / "structure-review.json"
    review_path.write_text(
        json.dumps(
            {
                "model_version": validate_structure_review.MODEL_VERSION,
                "suite_fingerprint": "current",
                "minimum_readable_count": 13,
                "reviewer": {
                    "midi_daw_experience": True,
                    "reviewed_at": "2026-08-07T00:00:00Z",
                },
                "results": [
                    {
                        "id": case["id"],
                        "rating": "direct_use" if index < 12 else "needs_redo",
                        "parser_validation": {"music21": {"status": "passed"}},
                    }
                    for index, case in enumerate(cases)
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validate_structure_review,
        "compute_structure_suite_fingerprint",
        lambda _root: "current",
    )

    result = validate_structure_review.validate(review_path, fixture_root)

    assert result["usable_count"] == 12
    assert result["passed"] is False
