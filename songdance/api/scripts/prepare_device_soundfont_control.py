"""Alternative renderer control; envelope and velocity response also change."""

import json
import subprocess
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import butter, sosfilt

from app.pipeline.audio import preprocess_audio
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def run():
    out = BATCH_ROOT / "10-device/soundfont-control"
    out.mkdir(exist_ok=False)
    midi = ROOT / "tests/fixtures/audio/generated/10-device.mid"
    font = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"
    command = [
        "fluidsynth",
        "-ni",
        "-R",
        "0",
        "-C",
        "0",
        "-g",
        "0.2",
        "-r",
        "22050",
        "-T",
        "wav",
        "-O",
        "float",
        "-F",
        str(out / "render.wav"),
        str(font),
        str(midi),
    ]
    with (out / "render.log").open("x") as log:
        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
    audio, rate = sf.read(out / "render.wav", always_2d=True)
    if rate != 22050 or len(audio) < 30 * rate:
        raise ValueError("unexpected render length/rate")
    mono = audio[: 30 * rate].mean(axis=1)
    if np.max(abs(mono)) <= 0:
        raise ValueError("empty render")
    mono *= 0.82 / np.max(abs(mono))
    filtered = sosfilt(butter(4, [180, 5500], btype="bandpass", fs=rate, output="sos"), mono)
    noisy = filtered + np.random.default_rng(1009).normal(0, 0.01, size=mono.shape).astype(
        "float32"
    )
    sf.write(out / "device.wav", np.clip(noisy, -1, 1), rate, subtype="PCM_16")
    preprocess_audio(out / "device.wav", out / "normalized.wav")
    normalized, normalized_rate = sf.read(out / "normalized.wav", dtype="int16")
    if normalized_rate != rate:
        raise ValueError("unexpected normalization rate")
    sf.write(
        out / "padded.wav",
        np.concatenate((np.zeros(rate, dtype="int16"), normalized, np.zeros(rate, dtype="int16"))),
        rate,
        subtype="PCM_16",
    )
    report = {
        "production_eligible": False,
        "source_midi_sha256": file_sha256(midi),
        "soundfont_sha256": file_sha256(font),
        "command": command,
        "script_sha256": file_sha256(Path(__file__)),
        "preprocessor_sha256": file_sha256(ROOT / "app/pipeline/audio.py"),
        "limitation": "renderer, envelope, timbre and velocity response all change",
        "artifacts": {p.name: file_sha256(p) for p in out.glob("*.wav")},
    }
    (out / "input.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
