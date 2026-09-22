"""Research-only additions from a second model, with explicit harmonic abstention."""

import json
import math
from pathlib import Path

import pretty_midi
import soundfile as sf

from scripts.audit_device_bass_audio import evidence
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def propose(audio, rate, retained, secondary):
    candidates = note_metrics(retained, secondary, 0.1)["unmatched_estimated_notes"]
    audit = []
    additions = []
    for candidate in candidates:
        measurement = evidence(audio, rate, candidate)
        competing = [
            n
            for n in [*retained, *secondary]
            if n["pitch"] < candidate["pitch"]
            and n["start_sec"] <= candidate["start_sec"] + 0.08
            and n["end_sec"] >= candidate["start_sec"] - 0.08
            and any(
                abs(candidate["pitch"] - n["pitch"] - 12 * math.log2(h)) <= 0.35
                for h in range(2, 7)
            )
        ]
        accept = (
            not competing
            and measurement["after_amplitude"] is not None
            and measurement["after_amplitude"] >= 0.001
            and measurement["before_amplitude"] is not None
            and measurement["before_amplitude"] <= measurement["after_amplitude"] / 4
        )
        audit.append(
            {
                "candidate": candidate,
                "measurement": measurement,
                "competing_lower_events": competing,
                "decision": "experimental_add" if accept else "abstain",
            }
        )
        if accept:
            additions.append(dict(candidate))
    return sorted([*retained, *additions], key=lambda n: (n["start_sec"], n["pitch"])), audit


def run():
    root = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1"
    comparison_path = root / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    prior_path = root / "reattack-v1/audit.json"
    prior = json.loads(prior_path.read_text())
    if prior["comparison_sha256"] != file_sha256(comparison_path):
        raise ValueError("reattack comparison changed")
    for name, digest in comparison["artifacts_sha256"].items():
        if file_sha256(root / name) != digest:
            raise ValueError("source artifacts changed")
    if prior["candidate_midi_sha256"] != file_sha256(root / "reattack-v1/candidate.mid"):
        raise ValueError("reattack MIDI changed")
    audio, rate = sf.read(root / "normalized.wav")
    events, audit = propose(audio, rate, prior["events"], comparison["models"]["basic"]["events"])
    out = root / "missing-notes-v2"
    out.mkdir(exist_ok=False)
    midi = pretty_midi.PrettyMIDI()
    instrument = pretty_midi.Instrument(0)
    instrument.notes = [
        pretty_midi.Note(n["velocity"], n["pitch"], n["start_sec"], n["end_sec"]) for n in events
    ]
    midi.instruments.append(instrument)
    midi.write(str(out / "candidate.mid"))
    reference_path = (
        ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-source-v1/reference.mid"
    )
    if file_sha256(reference_path) != comparison["reference_sha256"]:
        raise ValueError("reference changed")
    reference = read_midi(reference_path)
    report = {
        "production_eligible": False,
        "status": "experimental_not_teacher_approved",
        "prior_sha256": file_sha256(prior_path),
        "comparison_sha256": file_sha256(comparison_path),
        "script_sha256": file_sha256(Path(__file__)),
        "evidence_sha256": file_sha256(ROOT / "scripts/audit_device_bass_audio.py"),
        "metric_sha256": file_sha256(ROOT / "scripts/compare_piano_model_outputs.py"),
        "midi_sha256": file_sha256(out / "candidate.mid"),
        "events": events,
        "audit": audit,
        "metrics": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
        "limitation": "one synthetic fixture; amplitude growth is not physical attack certainty",
    }
    (out / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(
        "candidates", len(audit), "added", sum(x["decision"] == "experimental_add" for x in audit)
    )
    print(
        {k: report["metrics"]["0.05"][k] for k in ("matched_count", "extra_count", "missing_count")}
    )


if __name__ == "__main__":
    run()
