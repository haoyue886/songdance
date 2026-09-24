"""Run isolated continuity controls and all raw 16 events; never write a score."""

import argparse
import json

import numpy as np
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from app.pipeline.transcribe import NoteEvent
from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, source_events, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256
from scripts.polyphony_partial_probe import MAX_ERROR, MIN_TRACKS, measure


def control(pitch, level, phase, noise):
    rate = 22050
    times = np.arange(2 * rate) / rate
    audio = np.random.default_rng(16).normal(0, noise, len(times))
    for p, start, amplitude, angle in (
        (pitch, 0.2, 0.5, 0),
        (pitch + 12, 0.8, 0.3, 0),
        (pitch, 0.8, level, phase),
    ):
        x = times - start
        active = x >= 0
        local = x[active]
        env = np.minimum(local / 0.008, 1) * np.exp(-2.6 * local)
        for h in range(1, 7):
            audio[active] += (
                amplitude
                * env
                * np.sin(2 * np.pi * 440 * 2 ** ((p - 69) / 12) * h * local + angle)
                / h**1.35
            )
    events = [
        NoteEvent(0.2, 0.8, pitch, 80, 0),
        NoteEvent(0.8, 1.2, pitch, 40, 0),
        NoteEvent(0.8, 1.2, pitch + 12, 70, 0),
    ]
    return audio * 0.4, rate, events


def run(output):
    paths = verify_inputs(FIXTURES, json.loads(CONTRACT.read_text()))["16-noisy-polyphony"]
    output.mkdir(parents=True, exist_ok=False)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        controls = []
        for pitch in (55, 60, 64):
            for level in (0, 0.01, 0.04):
                for phase in (0, 1.57):
                    for noise in (0, 0.0001):
                        audio, rate, events = control(pitch, level, phase, noise)
                        controls.append(
                            {
                                "pitch": pitch,
                                "level": level,
                                "phase": phase,
                                "noise": noise,
                                "truth": "decay" if level == 0 else "restrike",
                                "measurement": measure(audio, rate, events[1], events),
                            }
                        )
        preprocess_audio(paths["source_wav"], output / "normalized.wav")
        audio, rate = sf.read(output / "normalized.wav")
        raw = read_midi(paths["original/raw.mid"])
        events = [
            NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], 0) for n in raw
        ]
        measured = [
            {"input_index": i, "event": raw[i], "measurement": measure(audio, rate, e, events)}
            for i, e in enumerate(events)
        ]
        reference, reproduction = source_events(FIXTURES, "16-noisy-polyphony", paths["source_wav"])
        metrics = note_metrics(reference, raw, 0.1)
        matched = {m["estimated_index"] for m in metrics["matches"]}
        selected = [r["input_index"] for r in measured if r["measurement"]["continuous_hypothesis"]]
        false_controls = sum(
            c["truth"] == "restrike" and c["measurement"]["continuous_hypothesis"] for c in controls
        )
        report = {
            "production_eligible": False,
            "actual_applied_deletions": 0,
            "scope": "additive synthetic controls and local audio only; not piano generalization",
            "thresholds": {"max_error": MAX_ERROR, "min_tracks": MIN_TRACKS},
            "inputs": {k: file_sha256(v) for k, v in paths.items()},
            "code": {
                p: file_sha256(ROOT / p)
                for p in (
                    "scripts/polyphony_partial_probe.py",
                    "scripts/run_polyphony_partial_probe.py",
                    "app/pipeline/crossing_attack_evidence.py",
                    "scripts/audit_teacher_reviews_15_16.py",
                    "scripts/generate_regression_set.py",
                    "scripts/compare_piano_model_outputs.py",
                    "app/pipeline/audio.py",
                )
            },
            "source_reconstruction": reproduction,
            "controls": controls,
            "events": measured,
            "control_restrike_false_selections": false_controls,
            "selected_indices": selected,
            "matched_onsets_selected": len(set(selected) & matched),
            "metrics_onsets_only": metrics,
            "conclusion": "rejected"
            if false_controls or set(selected) & matched
            else "limited_experiment_only_no_deletion_authorized",
        }
        (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        status.write_text('{"status":"complete","production_eligible":false}')
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in (
                        "conclusion",
                        "control_restrike_false_selections",
                        "selected_indices",
                        "matched_onsets_selected",
                    )
                }
            )
        )
        return report
    except Exception as error:
        status.write_text(
            json.dumps({"status": "failed", "error": str(error), "production_eligible": False})
        )
        raise


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
