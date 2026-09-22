import json

import numpy as np
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def test_soundfont_control_recomputes_all_notes_and_preserves_padded_samples():
    root = BATCH_ROOT / "10-device/soundfont-control"
    inputs = json.loads((root / "input.json").read_text())
    reference_path = ROOT / "tests/fixtures/audio/generated/10-device.mid"
    assert inputs["source_midi_sha256"] == file_sha256(reference_path)
    for name, digest in inputs["artifacts"].items():
        assert file_sha256(root / name) == digest
    y, rate = sf.read(root / "normalized.wav", dtype="int16")
    z, padded_rate = sf.read(root / "padded.wav", dtype="int16")
    assert rate == padded_rate == 22050
    assert np.array_equal(y, z[rate : rate + len(y)])
    assert len(y) == 30 * rate
    report = json.loads((root / "evaluation.json").read_text())
    receipt = json.loads((root / "transkun/inference.json").read_text())
    assert receipt["input_sha256"] == file_sha256(root / "padded.wav")
    assert receipt["midi_sha256"] == file_sha256(root / "transkun/raw.mid")
    events, clipped, rejected = restore(read_midi(root / "transkun/raw.mid"), 1, 30)
    assert events == report["events"]
    assert clipped == report["clipped"] and rejected == report["rejected"]
    reference = read_midi(reference_path)
    assert report["metrics"] == {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)}
    assert report["metrics"]["0.05"]["matched_count"] == 90
    assert report["metrics"]["0.05"]["missing_count"] == 0
    assert report["metrics"]["0.05"]["extra_count"] == 0
    assert report["production_eligible"] is False
