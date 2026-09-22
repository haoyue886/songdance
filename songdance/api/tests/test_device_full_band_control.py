import json

import numpy as np
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def test_full_band_control_preserves_source_reconstruction_and_binds_inference():
    root = BATCH_ROOT / "10-device/full-band-control"
    inputs = json.loads((root / "input.json").read_text())
    original = ROOT / "tests/fixtures/audio/generated/10-device.wav"
    assert inputs["source_sha256"] == file_sha256(original)
    a, rate = sf.read(original, dtype="int16")
    b, r = sf.read(root / "reconstructed.wav", dtype="int16")
    assert rate == r and np.array_equal(a, b)
    for name, digest in inputs["artifacts"].items():
        assert digest == file_sha256(root / name)
    y, rate = sf.read(root / "normalized.wav", dtype="int16")
    padded, r = sf.read(root / "padded.wav", dtype="int16")
    assert r == rate and np.array_equal(y, padded[rate : rate + len(y)])
    receipt = json.loads((root / "transkun/inference.json").read_text())
    assert receipt["input_sha256"] == file_sha256(root / "padded.wav")
    assert receipt["midi_sha256"] == file_sha256(root / "transkun/raw.mid")
    report = json.loads((root / "evaluation.json").read_text())
    events, clipped, rejected = restore(read_midi(root / "transkun/raw.mid"), 1, 30)
    assert events == report["events"]
    assert clipped == report["clipped"] and rejected == report["rejected"]
    reference = read_midi(ROOT / "tests/fixtures/audio/generated/10-device.mid")
    assert report["metrics"] == {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)}
    assert report["production_eligible"] is False
