"""Evaluate a shifted-input inference in original time; no note-level fusion."""

import json
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256

BOUNDARY_TOLERANCE_SECONDS = 0.01


def restore(notes, prefix, duration):
    kept, clipped, rejected = [], [], []
    for note in notes:
        start, end = note["start_sec"] - prefix, note["end_sec"] - prefix
        if start < -BOUNDARY_TOLERANCE_SECONDS or start >= duration or end <= max(0, start):
            rejected.append(note)
            continue
        event = {**note, "start_sec": max(0.0, start), "end_sec": min(end, duration)}
        kept.append(event)
        if end > duration or start < 0:
            clipped.append({"before": note, "after": event})
    return kept, clipped, rejected


def run():
    root = BATCH_ROOT / "10-device"
    experiment = root / "context-shift-4s"
    if any((experiment / name).exists() for name in ("evaluation-v2.json", "aligned-v2.mid")):
        raise ValueError("v2 output exists; preserve previous artifacts")
    receipt = json.loads((experiment / "input.json").read_text())
    inference = json.loads((experiment / "transkun/inference.json").read_text())
    source = root / "basic-pitch/normalized.wav"
    padded = experiment / "padded.wav"
    raw = experiment / "transkun/raw.mid"
    assert receipt["source_sha256"] == file_sha256(source)
    assert receipt["padded_sha256"] == inference["input_sha256"] == file_sha256(padded)
    assert inference["status"] == "inference_complete"
    assert inference["midi_sha256"] == file_sha256(raw)
    assert inference["adapter_sha256"] == file_sha256(
        ROOT / "experiments/models/transkun/run_cpu.py"
    )
    y, rate = sf.read(source, dtype="int16")
    z, padded_rate = sf.read(padded, dtype="int16")
    prefix = receipt["prefix_seconds"]
    assert rate == padded_rate == receipt["sample_rate"]
    assert np.array_equal(y, z[prefix * rate : prefix * rate + len(y)])
    notes, clipped, rejected = restore(read_midi(raw), prefix, len(y) / rate)
    reference_path = ROOT / "tests/fixtures/audio/generated/10-device.mid"
    reference = read_midi(reference_path)
    old = read_midi(root / "transkun-v2/raw.mid")
    report = {
        "production_eligible": False,
        "boundary_tolerance_seconds": BOUNDARY_TOLERANCE_SECONDS,
        "input": receipt,
        "inference_receipt_sha256": file_sha256(experiment / "transkun/inference.json"),
        "evaluator_sha256": file_sha256(Path(__file__)),
        "reference_sha256": file_sha256(reference_path),
        "baseline_midi_sha256": file_sha256(root / "transkun-v2/raw.mid"),
        "clipped": clipped,
        "rejected_outside_original_onsets": rejected,
        "restored_events": notes,
        "baseline": {str(t): note_metrics(reference, old, t) for t in (0.05, 0.1)},
        "shifted": {str(t): note_metrics(reference, notes, t) for t in (0.05, 0.1)},
        "limitation": "single synthetic clip; shifted context is not proof of independent attack",
    }
    baseline_bass = [n for n in old if n["pitch"] < 60]
    shifted_bass = [n for n in notes if n["pitch"] < 60]
    differences = note_metrics(baseline_bass, shifted_bass, 0.1)
    report["unscored_bass_consistency"] = {
        "tolerance_seconds": 0.1,
        "shared_count": differences["matched_count"],
        "baseline_only": differences["missing_reference_notes"],
        "shifted_only": differences["unmatched_estimated_notes"],
        "note": "model agreement is not correctness; no note fusion performed",
    }
    with (experiment / "evaluation-v2.json").open("x") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    midi = pretty_midi.PrettyMIDI()
    piano = pretty_midi.Instrument(0)
    piano.notes = [
        pretty_midi.Note(n["velocity"], n["pitch"], n["start_sec"], n["end_sec"]) for n in notes
    ]
    midi.instruments.append(piano)
    midi.write(str(experiment / "aligned-v2.mid"))
    for model in ("baseline", "shifted"):
        for tol, m in report[model].items():
            print(
                model,
                tol,
                {
                    k: m[k]
                    for k in ("estimated_count", "matched_count", "extra_count", "missing_count")
                },
            )


if __name__ == "__main__":
    run()
