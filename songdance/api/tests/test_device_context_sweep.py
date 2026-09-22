import json
from pathlib import Path

import pytest

from scripts import sweep_device_context as sweep
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def test_failed_inference_leaves_failure_record_and_refuses_overwrite(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("controlled inference failure")

    monkeypatch.setattr(sweep.subprocess, "run", fail)
    output = tmp_path / "experiment"
    with pytest.raises(RuntimeError, match="controlled"):
        sweep.run(Path("/unused/python"), Path("/unused/source"), output)
    assert json.loads((output / "prefix-1/status.json").read_text())["status"] == "failed"
    assert not (output / "summary.json").exists()
    with pytest.raises(FileExistsError):
        sweep.run(Path("/unused/python"), Path("/unused/source"), output)


@pytest.mark.parametrize("prefix", (1, 2, 6, 8))
def test_actual_trial_metrics_recompute_from_raw_midi(prefix):
    root = BATCH_ROOT / "10-device/context-sweep-v1"
    folder = root / f"prefix-{prefix}"
    report = json.loads((folder / "evaluation.json").read_text())
    receipt = json.loads((folder / "transkun/inference.json").read_text())
    assert receipt["input_sha256"] == file_sha256(folder / "input.wav")
    assert receipt["midi_sha256"] == file_sha256(folder / "transkun/raw.mid")
    notes, clipped, rejected = restore(read_midi(folder / "transkun/raw.mid"), prefix, 30)
    assert notes == report["events"]
    assert clipped == report["clipped"]
    assert rejected == report["rejected"]
    reference = read_midi(ROOT / "tests/fixtures/audio/generated/10-device.mid")
    assert report["metrics"] == {str(t): note_metrics(reference, notes, t) for t in (0.05, 0.1)}
