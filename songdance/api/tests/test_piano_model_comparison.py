import importlib.util
import json
from pathlib import Path

import pytest

from scripts import compare_piano_model_outputs as comparison


def event(pitch, start, end=None):
    return {
        "pitch": pitch,
        "start_sec": start,
        "end_sec": start + 0.4 if end is None else end,
        "velocity": 80,
    }


def test_raw_evaluation_counts_wrong_pitches_extra_notes_and_misses_without_quantization():
    reference = [event(60, 0), event(64, 0.5), event(67, 1)]
    estimated = [event(60, 0.04), event(76, 0.5), event(60, 0.5)]
    result = comparison.note_metrics(reference, estimated, 0.05)
    assert result["matched_count"] == 1
    assert result["extra_count"] == result["missing_count"] == 2
    assert result["precision"] == result["recall"] == pytest.approx(1 / 3)
    assert result["matches"][0]["onset_error_seconds"] == 0.04
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_tolerance_change_is_reported_separately():
    reference, estimated = [event(60, 0)], [event(60, 0.075)]
    assert comparison.note_metrics(reference, estimated, 0.05)["matched_count"] == 0
    assert comparison.note_metrics(reference, estimated, 0.1)["matched_count"] == 1


def test_empty_inference_is_failure_to_recall_not_a_perfect_score():
    result = comparison.note_metrics([event(60, 0)], [], 0.1)
    assert result["precision"] == result["recall"] == result["f1"] == 0
    assert result["missing_count"] == 1


def test_wrong_or_incomplete_inference_input_is_rejected(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.mkdir()
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    (baseline / "inference.json").write_text(
        '{"status":"inference_complete","input_sha256":"baseline"}'
    )
    (baseline / "normalized.wav").write_bytes(b"actual baseline input")
    monkeypatch.setattr(comparison, "BASELINE", baseline)
    for receipt in (
        {"status": "failed"},
        {"status": "inference_complete", "input_sha256": "wrong"},
    ):
        (model / "inference.json").write_text(json.dumps(receipt))
        with pytest.raises(ValueError):
            comparison.compare(model, tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()


def test_isolated_runner_refuses_to_overwrite_a_previous_result(tmp_path):
    path = Path(__file__).parents[1] / "experiments/models/transkun/run_cpu.py"
    spec = importlib.util.spec_from_file_location("transkun_runner", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    output = tmp_path / "existing"
    output.mkdir()
    (output / "raw.mid").write_bytes(b"preserve")
    with pytest.raises(ValueError, match="empty output"):
        runner.run(tmp_path, tmp_path / "unused.json", tmp_path / "unused.wav", output)
    assert (output / "raw.mid").read_bytes() == b"preserve"


def test_report_cannot_overwrite_an_input_or_previous_report(tmp_path):
    destination = tmp_path / "inference.json"
    destination.write_text("preserve")
    with pytest.raises(ValueError, match="overwrite"):
        comparison.compare(tmp_path, destination)
    assert destination.read_text() == "preserve"


def test_source_validation_failure_is_saved_and_cannot_appear_as_success(tmp_path):
    path = Path(__file__).parents[1] / "experiments/models/transkun/run_cpu.py"
    spec = importlib.util.spec_from_file_location("transkun_failure_runner", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    output = tmp_path / "failed"
    with pytest.raises(FileNotFoundError):
        runner.run(tmp_path, tmp_path / "missing-manifest.json", tmp_path / "input.wav", output)
    receipt = json.loads((output / "inference.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["production_eligible"] is False
    assert not (output / "raw.mid").exists()


def test_candidate_receipt_cannot_relabel_a_replaced_basic_pitch_input(tmp_path, monkeypatch):
    baseline = tmp_path / "basic"
    candidate = tmp_path / "candidate"
    baseline.mkdir()
    candidate.mkdir()
    audio = baseline / "normalized.wav"
    audio.write_bytes(b"replaced audio")
    (baseline / "inference.json").write_text(
        json.dumps(
            {
                "status": "inference_complete",
                "input_sha256": "original audio hash",
            }
        )
    )
    (candidate / "inference.json").write_text(
        json.dumps(
            {
                "status": "inference_complete",
                "input_sha256": comparison.file_sha256(audio),
            }
        )
    )
    monkeypatch.setattr(comparison, "BASELINE", baseline)
    with pytest.raises(ValueError, match="identical normalized"):
        comparison.compare(candidate, tmp_path / "report.json")


def test_actual_model_comparison_is_bound_to_raw_outputs_and_recomputes_metrics(tmp_path):
    root = comparison.BASELINE.parent
    original = json.loads((root / "comparison.json").read_text())
    rebuilt = comparison.compare(root / "transkun-v2", tmp_path / "comparison.json")
    assert rebuilt == original
    assert rebuilt["distinct_reference_count"] == 111
    assert rebuilt["source_midi_count"] == 118
    assert rebuilt["production_eligible"] is False
    assert rebuilt["transkun_inference"]["device"] == "cpu"
    assert rebuilt["transkun_inference"]["input_frames"] == 661500
    assert rebuilt["transkun_inference"]["model_frames"] == 1323000
    for tolerance in ("0.05", "0.1"):
        basic, candidate = rebuilt["basic_pitch_raw"][tolerance], rebuilt["transkun_raw"][tolerance]
        assert basic["estimated_count"] == 285
        assert basic["matched_count"] == 111
        assert basic["extra_count"] == 174
        assert candidate["estimated_count"] == candidate["matched_count"] == 105
        assert candidate["extra_count"] == 0
        assert candidate["missing_count"] == len(candidate["missing_reference_notes"]) == 6
        assert candidate["f1"] == pytest.approx(0.9722222222222222)


@pytest.mark.parametrize("stage", ["preprocess", "inference"])
def test_basic_pitch_failure_is_recorded_and_cannot_be_reused_as_success(
    tmp_path, monkeypatch, stage
):
    from scripts import prepare_piano_model_input as prepare

    def fail(*args):
        raise RuntimeError("test failure")

    if stage == "preprocess":
        monkeypatch.setattr(prepare, "preprocess_audio", fail)
    else:
        monkeypatch.setattr(
            prepare, "preprocess_audio", lambda source, dest: dest.write_bytes(b"test")
        )
        monkeypatch.setattr(prepare, "transcribe_audio", fail)
    output = tmp_path / "failed-basic"
    with pytest.raises(RuntimeError, match="test failure"):
        prepare.run(output)
    assert json.loads((output / "inference.json").read_text())["status"] == "failed"
    with pytest.raises(ValueError, match="empty"):
        prepare.run(output)


def test_wrong_source_commit_is_rejected_before_extracting_archive(tmp_path):
    path = Path(__file__).parents[1] / "experiments/models/transkun/verify_source.py"
    spec = importlib.util.spec_from_file_location("verify_transkun_source", path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps({"sha": "0" * 40}))
    with pytest.raises(ValueError, match="pinned commit"):
        verifier.verify(
            tmp_path / "unused.tar.gz", tree, tmp_path / "source", tmp_path / "manifest"
        )
    assert not (tmp_path / "source").exists()


@pytest.mark.parametrize("target", ["transcribe.py", "raw.mid"])
def test_basic_pitch_changed_transcriber_or_midi_is_rejected(tmp_path, monkeypatch, target):
    original_hash = comparison.file_sha256

    def changed_hash(path):
        if path.name == target and (target != "raw.mid" or path.parent == comparison.BASELINE):
            return "changed"
        return original_hash(path)

    monkeypatch.setattr(comparison, "file_sha256", changed_hash)
    root = comparison.BASELINE.parent
    with pytest.raises(ValueError, match="recorded code|artifact changed"):
        comparison.compare(root / "transkun-v2", tmp_path / "report.json")
    assert not (tmp_path / "report.json").exists()
