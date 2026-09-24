"""Evaluate existing harmonic deletion on repeated notes; no relaxed thresholds."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.crossing_harmonic_probes import paired_wave
from scripts.piano_comparison_cases import ROOT, file_sha256


def selected_indices(events, evidence):
    if evidence.status != "available":
        raise ValueError("audio evidence unavailable")
    return [i for i, e in enumerate(events) if any(r.matches(e) for r in evidence.removals)]


def weak_repeat(amplitude):
    rate = 22050
    time = np.arange(2 * rate) / rate
    audio = np.zeros_like(time)
    for pitch, start, level in [(60, 0.2, 0.5), (60, 0.45, amplitude), (64, 0.45, 0.4)]:
        x = time - start
        mask = x >= 0
        local = x[mask]
        envelope = np.minimum(local / 0.008, 1) * np.exp(-8 * local)
        for harmonic in range(1, 7):
            audio[mask] += (
                level
                * envelope
                * np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * harmonic * local)
                / harmonic**1.35
            )
    events = [
        NoteEvent(0.2, 0.45, 60, 85, 0.7),
        NoteEvent(0.45, 0.7, 60, 35, 0.3),
        NoteEvent(0.45, 0.7, 64, 80, 0.7),
    ]
    return audio * 0.4, rate, events


def run(output):
    if output.exists():
        raise ValueError("output exists")
    bindings = verify_inputs(FIXTURES, json.loads(CONTRACT.read_text()))["15-repeated-notes"]
    output.mkdir(parents=True)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        preprocess_audio(bindings["source_wav"], output / "normalized.wav")
        raw = read_midi(bindings["original/raw.mid"])
        events = [
            NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], n["velocity"] / 127)
            for n in raw
        ]
        evidence = extract_harmonic_evidence(output / "normalized.wav", events)
        indices = selected_indices(events, evidence)
        kept = [n for i, n in enumerate(raw) if i not in indices]
        controls = []
        for pitch in (60, 62, 64, 67):
            for level in (0, 0.04, 0.16):
                audio, rate, notes = paired_wave(pitch, 12, level, 0, 0.25)
                name = f"octave-{pitch}-{level}.wav"
                sf.write(output / name, audio, rate, subtype="FLOAT")
                measured = extract_harmonic_evidence(output / name, notes)
                selection = selected_indices(notes, measured)
                controls.append(
                    {
                        "id": name,
                        "kind": "pure_partial" if level == 0 else "real_octave",
                        "real_indices": [0] if level == 0 else [0, 1],
                        "selected": selection,
                        "events": [asdict(n) for n in notes],
                        "evidence": measured.summary(),
                        "sha256": file_sha256(output / name),
                    }
                )
        for level in (0.01, 0.04, 0.16):
            audio, rate, notes = weak_repeat(level)
            name = f"weak-repeat-{level}.wav"
            sf.write(output / name, audio, rate, subtype="FLOAT")
            measured = extract_harmonic_evidence(output / name, notes)
            controls.append(
                {
                    "id": name,
                    "kind": "real_weak_repeat",
                    "real_indices": [0, 1, 2],
                    "selected": selected_indices(notes, measured),
                    "events": [asdict(n) for n in notes],
                    "evidence": measured.summary(),
                    "sha256": file_sha256(output / name),
                }
            )
        # Only after selecting candidates do we consult source truth.
        reference = read_midi(bindings["source_midi"])
        false_deletions = sum(len(set(c["real_indices"]) & set(c["selected"])) for c in controls)
        result = {
            "production_eligible": False,
            "actual_applied_deletions": 0,
            "event_source": "raw MIDI; velocity-derived placeholder is not calibrated confidence",
            "control_event_source": "synthetic event hypotheses, not model inference",
            "source_sha256": file_sha256(bindings["source_wav"]),
            "raw_sha256": file_sha256(bindings["original/raw.mid"]),
            "reference_sha256": file_sha256(bindings["source_midi"]),
            "code_sha256": {
                p: file_sha256(ROOT / p)
                for p in (
                    "scripts/audit_repeated_harmonics.py",
                    "scripts/crossing_harmonic_probes.py",
                    "app/pipeline/harmonics.py",
                    "app/pipeline/audio.py",
                )
            },
            "evidence": evidence.summary(),
            "hypothetical_deleted_indices": indices,
            "before": note_metrics(reference, raw, 0.1),
            "after": note_metrics(reference, kept, 0.1),
            "controls": controls,
            "control_real_note_deletions": false_deletions,
            "conclusion": "unsafe_on_controls"
            if false_deletions
            else "limited_controls_only_no_production_approval",
        }
        (output / "audit.json").write_text(json.dumps(result, indent=2, allow_nan=False))
        status.write_text('{"status":"complete","production_eligible":false}')
        print(
            "selected",
            len(indices),
            "extra remaining",
            result["after"]["extra_count"],
            "missing",
            result["after"]["missing_count"],
            "control false deletions",
            false_deletions,
        )
        return result
    except Exception as error:
        status.write_text(json.dumps({"status": "failed", "error": str(error)}))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
