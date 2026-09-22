import json

import pytest

from scripts import compare_piano_model_outputs as comparison
from scripts import piano_comparison_cases as cases


@pytest.mark.parametrize("case_id", cases.CASE_IDS)
def test_each_actual_case_report_recomputes_without_relabeling(tmp_path, case_id):
    root = cases.BATCH_ROOT / case_id
    result = comparison.compare(
        root / "transkun-v2",
        tmp_path / "report.json",
        case_id=case_id,
        baseline=root / "basic-pitch",
    )
    assert result == json.loads((root / "comparison.json").read_text())
    assert result["case_id"] == case_id
    assert result["production_eligible"] is False
    if case_id == "02-brahms-intermezzo":
        assert result["reference_sha256"] is None
        assert result["distinct_reference_count"] is None
        assert result["basic_pitch_raw"] is result["transkun_raw"] is None
        differences = result["unscored_model_differences"]
        for data in differences.values():
            assert not {"precision", "recall", "f1", "extra_count", "missing_count"} & data.keys()
            assert data["basic_pitch_count"] == (
                data["shared_pitch_onset_count"] + len(data["basic_pitch_only"])
            )
            assert data["transkun_count"] == (
                data["shared_pitch_onset_count"] + len(data["transkun_only"])
            )
    else:
        assert result["distinct_reference_count"] > 0
        assert "unscored_model_differences" not in result


def test_mismatched_case_cannot_borrow_other_baseline_or_reference(tmp_path):
    root = cases.BATCH_ROOT / "14-hand-crossing"
    with pytest.raises(ValueError, match="different case"):
        comparison.compare(
            root / "transkun-v2",
            tmp_path / "report.json",
            case_id="06-sustain",
            baseline=root / "basic-pitch",
        )
    assert not (tmp_path / "report.json").exists()


def test_unknown_case_is_not_accepted():
    with pytest.raises(ValueError, match="unsupported"):
        cases.case_inputs("../14-hand-crossing")


def test_real_recording_without_reference_has_verified_provenance():
    wav, midi, provenance = cases.case_inputs("02-brahms-intermezzo")
    assert midi is None
    assert cases.file_sha256(wav) == provenance["record"]["clip_sha256"]


@pytest.mark.parametrize("mutation", ["audio", "license"])
def test_changed_real_audio_or_unapproved_license_is_rejected(tmp_path, monkeypatch, mutation):
    case_id = "02-brahms-intermezzo"
    (tmp_path / "human-generated").mkdir()
    wav = tmp_path / "human-generated" / f"{case_id}.wav"
    wav.write_bytes(b"fixture")
    entry = {
        "id": case_id,
        "clip_sha256": "wrong" if mutation == "audio" else cases.file_sha256(wav),
        "license": "unknown" if mutation == "license" else "Public domain",
    }
    (tmp_path / "human-provenance.json").write_text(json.dumps({"cases": [entry]}))
    monkeypatch.setattr(cases, "AUDIO_ROOT", tmp_path)
    with pytest.raises(ValueError, match="provenance|license"):
        cases.case_inputs(case_id)
