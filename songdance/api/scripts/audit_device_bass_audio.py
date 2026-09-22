"""Offline fundamental evidence, not an onset detector or note fusion rule."""

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import BATCH_ROOT, file_sha256


def amplitude(audio, rate, pitch, center):
    count = round(0.2 * rate)
    left = round(center * rate) - count // 2
    if left < 0 or left + count > len(audio):
        return None
    time = np.arange(count) / rate
    window = np.hanning(count)
    frequency = 440 * 2 ** ((pitch - 69) / 12)
    # A 200ms window has approximately 5Hz resolution; no independent-attack claim.
    return float(
        2
        * abs(np.sum(audio[left : left + count] * window * np.exp(-2j * np.pi * frequency * time)))
        / sum(window)
    )


def evidence(audio, rate, event):
    onset, pitch = event["start_sec"], event["pitch"]
    before = amplitude(audio, rate, pitch, onset - 0.15)
    after = amplitude(audio, rate, pitch, onset + 0.15)
    return {
        "event": event,
        "before_amplitude": before,
        "after_amplitude": after,
        "amplitude_ratio": after / before if before and after is not None else None,
        "independent_attack_confirmed": False,
        "status": "boundary_unavailable" if before is None or after is None else "measurement_only",
    }


def run():
    root = BATCH_ROOT / "10-device"
    paths = {
        "audio": root / "basic-pitch/normalized.wav",
        "basic": root / "basic-pitch/raw.mid",
        "transkun": root / "transkun-v2/raw.mid",
    }
    audio, rate = sf.read(paths["audio"])
    if audio.ndim != 1:
        raise ValueError("requires mono input")
    basic = [n for n in read_midi(paths["basic"]) if n["pitch"] < 60]
    transkun = [n for n in read_midi(paths["transkun"]) if n["pitch"] < 60]
    candidates = note_metrics(transkun, basic, 0.1)["unmatched_estimated_notes"]
    report = {
        "production_eligible": False,
        "added_notes": 0,
        "limitation": "fundamental energy is not proof of an independent attack; no fusion",
        "input_sha256": {k: file_sha256(p) for k, p in paths.items()},
        "script_sha256": file_sha256(Path(__file__)),
        "window_seconds": 0.2,
        "events": [evidence(audio, rate, n) for n in candidates],
    }
    target = root / "bass-audio-evidence.json"
    with target.open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print("measured", len(candidates), "candidates; added notes: 0")


if __name__ == "__main__":
    run()
