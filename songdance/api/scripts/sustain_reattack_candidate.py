"""Research-only same-pitch reattack proposals; reference is only used for evaluation."""

import json
import math
from pathlib import Path

import pretty_midi
import soundfile as sf

from scripts.audit_device_bass_audio import evidence
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def rebuild(audio, rate, baseline, secondary):
    proposals = []
    for candidate in sorted(secondary, key=lambda n: n["start_sec"]):
        parents = [
            i
            for i, n in enumerate(baseline)
            if n["pitch"] == candidate["pitch"]
            and n["start_sec"] + 0.3 < candidate["start_sec"] < n["end_sec"] - 0.1
        ]
        if len(parents) != 1:
            continue
        measurement = evidence(audio, rate, candidate)
        competitors = [
            n
            for n in [*baseline, *secondary]
            if n["pitch"] < candidate["pitch"]
            and abs(n["start_sec"] - candidate["start_sec"]) <= 0.08
            and any(
                abs(candidate["pitch"] - n["pitch"] - 12 * math.log2(h)) <= 0.35
                for h in range(2, 7)
            )
        ]
        approved = (
            not competitors
            and measurement["after_amplitude"] is not None
            and measurement["after_amplitude"] >= 0.001
            and measurement["amplitude_ratio"] is not None
            and measurement["amplitude_ratio"] >= 4
        )
        proposals.append(
            {
                "parent_index": parents[0],
                "candidate": candidate,
                "measurement": measurement,
                "harmonic_competitors": competitors,
                "decision": "experimental_split" if approved else "retain",
            }
        )
    rebuilt = []
    for index, parent in enumerate(baseline):
        splits = {
            p["candidate"]["start_sec"]: p["candidate"]
            for p in proposals
            if p["parent_index"] == index and p["decision"] == "experimental_split"
        }
        current = dict(parent)
        for start, candidate in sorted(splits.items()):
            rebuilt.append({**current, "end_sec": start})
            current = {**parent, "start_sec": start, "velocity": candidate["velocity"]}
        rebuilt.append(current)
    return rebuilt, proposals


def run():
    source = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1"
    comparison_path = source / "comparison.json"
    comparison = json.loads(comparison_path.read_text())
    for name, digest in comparison["artifacts_sha256"].items():
        if file_sha256(source / name) != digest:
            raise ValueError("model comparison input changed")
    receipt_path = source / "transkun/inference.json"
    receipt = json.loads(receipt_path.read_text())
    if file_sha256(receipt_path) != comparison["transkun_receipt_sha256"] or receipt[
        "midi_sha256"
    ] != file_sha256(source / "transkun/raw.mid"):
        raise ValueError("Transkun input changed")
    audio, rate = sf.read(source / "normalized.wav")
    baseline = comparison["models"]["transkun"]["events"]
    secondary = comparison["models"]["basic"]["events"]
    events, proposals = rebuild(audio, rate, baseline, secondary)
    output = source / "reattack-v1"
    output.mkdir(exist_ok=False)
    reference_path = (
        ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-source-v1/reference.mid"
    )
    if file_sha256(reference_path) != comparison["reference_sha256"]:
        raise ValueError("reference changed")
    reference = read_midi(reference_path)
    midi = pretty_midi.PrettyMIDI()
    piano = pretty_midi.Instrument(0)
    piano.notes = [
        pretty_midi.Note(n["velocity"], n["pitch"], n["start_sec"], n["end_sec"]) for n in events
    ]
    midi.instruments.append(piano)
    midi.write(str(output / "candidate.mid"))
    report = {
        "production_eligible": False,
        "comparison_sha256": file_sha256(comparison_path),
        "script_sha256": file_sha256(Path(__file__)),
        "evidence_script_sha256": file_sha256(ROOT / "scripts/audit_device_bass_audio.py"),
        "candidate_midi_sha256": file_sha256(output / "candidate.mid"),
        "proposals": proposals,
        "events": events,
        "metrics": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
        "limitation": "experimental thresholds; not proof of keystrokes; not production approved",
    }
    (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print(
        "proposals",
        len(proposals),
        "splits",
        sum(p["decision"] == "experimental_split" for p in proposals),
    )
    print(
        {k: report["metrics"]["0.05"][k] for k in ("matched_count", "extra_count", "missing_count")}
    )


if __name__ == "__main__":
    run()
