import json
import shutil

import pytest

import scripts.publish_public_example as publisher
from scripts.publish_public_example import CASE_ID, FIXTURE_ROOT, SOURCE_AUDIO


@pytest.mark.parametrize(
    ("field", "stale_value", "error"),
    [
        ("source_url", "https://example.invalid/score", "source metadata is not trusted"),
        ("download_url", "https://example.invalid/score.mid", "source metadata is not trusted"),
        ("sha256", "0" * 64, "MIDI fingerprint mismatch"),
        ("path", "missing.mid", "MIDI fingerprint mismatch"),
        ("measure_count", 72, "measure range is incomplete"),
    ],
)
def test_rejects_tampered_reference_score_contract(
    tmp_path, field: str, stale_value: object, error: str
) -> None:
    contract_path, contract = _copy_reference_fixture(tmp_path)
    contract["reference_score"][field] = stale_value
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        _validate_reference_fixture(contract_path)


@pytest.mark.parametrize(
    ("tamper", "error"),
    [
        ("missing", "audio reference mapping"),
        ("unordered", "audio reference mapping"),
        ("out_of_range", "audio reference mapping"),
        ("schema", "audio reference mapping"),
        ("evidence", "alignment evidence"),
    ],
)
def test_rejects_invalid_audio_reference_mapping(tmp_path, tamper: str, error: str) -> None:
    contract_path, contract = _copy_reference_fixture(tmp_path)
    mapping = contract["audio_reference_mapping"]["mapping"]
    if tamper == "missing":
        mapping.pop()
    elif tamper == "unordered":
        mapping[0], mapping[1] = mapping[1], mapping[0]
    elif tamper == "out_of_range":
        mapping[-1]["reference_measure_number"] = 74
    elif tamper == "schema":
        contract["audio_reference_mapping"]["schema_version"] = 2
    else:
        contract["audio_reference_mapping"]["alignment_evidence"]["method"] = "manual"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        _validate_reference_fixture(contract_path)


def test_rejects_timeline_with_missing_mapped_downbeat(tmp_path) -> None:
    contract_path, _contract = _copy_reference_fixture(tmp_path)
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    timeline = json.loads((source_root / "timeline.json").read_text(encoding="utf-8"))
    timeline["downbeat_grid_seconds"].pop()

    with pytest.raises(ValueError, match="timeline does not cover"):
        _validate_reference_fixture(contract_path, timeline)


def _copy_reference_fixture(tmp_path):
    contract_path = tmp_path / publisher.REFERENCE_CONTRACT_FILE.name
    reference_path = publisher.REFERENCE_CONTRACT_FILE.with_name("mozart-k545-complete.mid")
    shutil.copy2(publisher.REFERENCE_CONTRACT_FILE, contract_path)
    shutil.copy2(reference_path, tmp_path / reference_path.name)
    return contract_path, json.loads(contract_path.read_text(encoding="utf-8"))


def _validate_reference_fixture(contract_path, timeline=None) -> dict[str, object]:
    source_root = FIXTURE_ROOT / "human-review-artifacts" / CASE_ID
    if timeline is None:
        timeline = json.loads((source_root / "timeline.json").read_text(encoding="utf-8"))
    return publisher.validate_reference_contract(
        contract_path,
        CASE_ID,
        SOURCE_AUDIO,
        publisher._source_metadata(),
        timeline,
        source_root / "score.musicxml",
    )
