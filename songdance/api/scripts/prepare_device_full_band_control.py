"""Change only source bandwidth after verifying exact fixture reconstruction."""

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from scripts.generate_regression_set import synthesize, two_hand
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def run():
    output = BATCH_ROOT / "10-device/full-band-control"
    output.mkdir(exist_ok=False)
    original = ROOT / "tests/fixtures/audio/generated/10-device.wav"
    for name, band in [("reconstructed", True), ("full-band", False)]:
        sf.write(
            output / f"{name}.wav",
            synthesize(two_hand(), 30, 22050, 0.01, band, 1009),
            22050,
            subtype="PCM_16",
        )
    a, _ = sf.read(original, dtype="int16")
    b, _ = sf.read(output / "reconstructed.wav", dtype="int16")
    if not np.array_equal(a, b):
        raise ValueError("fixture has changed: cannot assert controlled bandwidth comparison")
    preprocess_audio(output / "full-band.wav", output / "normalized.wav")
    y, rate = sf.read(output / "normalized.wav", dtype="int16")
    sf.write(
        output / "padded.wav",
        np.concatenate((np.zeros(rate, dtype="int16"), y, np.zeros(rate, dtype="int16"))),
        rate,
        subtype="PCM_16",
    )
    report = {
        "production_eligible": False,
        "exact_source_reconstruction": True,
        "changed_factor": "source device bandpass disabled; same preprocessing then 1s padding",
        "source_sha256": file_sha256(original),
        "generator_sha256": file_sha256(ROOT / "scripts/generate_regression_set.py"),
        "script_sha256": file_sha256(Path(__file__)),
        "artifacts": {p.name: file_sha256(p) for p in output.glob("*.wav")},
    }
    (output / "input.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
