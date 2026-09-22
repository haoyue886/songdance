import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scripts import compare_sustain_triad_models as comparison
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import ROOT, file_sha256


def test_actual_triad_models_share_audio_and_recompute_all_metrics():
    output = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1"
    report = json.loads((output / "comparison.json").read_text())
    receipt = json.loads((output / "transkun/inference.json").read_text())
    assert report["input_sha256"] == receipt["input_sha256"] == file_sha256(output / "padded.wav")
    for name, digest in report["artifacts_sha256"].items():
        assert digest == file_sha256(output / name)
    assert receipt["midi_sha256"] == file_sha256(output / "transkun/raw.mid")
    y, rate = sf.read(output / "normalized.wav", dtype="int16")
    z, other = sf.read(output / "padded.wav", dtype="int16")
    assert rate == other == 22050 and np.array_equal(y, z[rate:-rate])
    reference = read_midi(comparison.SOURCE / "reference.mid")
    assert len(reference) == 45
    for model, raw in [
        ("basic", json.loads((output / "basic-raw.json").read_text())),
        ("transkun", read_midi(output / "transkun/raw.mid")),
    ]:
        mapped, clipped, rejected = restore(raw, 1, 30)
        row = report["models"][model]
        assert row["events"] == mapped and row["clipped"] == clipped and row["rejected"] == rejected
        assert row["metrics"] == {str(t): note_metrics(reference, mapped, t) for t in (0.05, 0.1)}
    assert report["production_eligible"] is False


def test_failed_preprocessing_is_retained_and_cannot_be_overwritten(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(comparison, "preprocess_audio", fail)
    output = tmp_path / "experiment"
    with pytest.raises(RuntimeError, match="controlled"):
        comparison.run(output, Path("/unused"), Path("/unused"))
    assert json.loads((output / "status.json").read_text())["status"] == "failed"
    with pytest.raises(FileExistsError):
        comparison.run(output, Path("/unused"), Path("/unused"))
