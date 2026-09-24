"""Measure coverage on a bound real recording, without inventing note truth."""

import argparse
import json
from collections import Counter
from pathlib import Path

import soundfile as sf

from app.pipeline.transcribe import NoteEvent
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, case_inputs, file_sha256
from scripts.polyphony_partial_probe import MAX_ERROR, MIN_TRACKS, measure

CASE = "02-brahms-intermezzo"


def verify(baseline: Path) -> tuple[dict, list[dict]]:
    wav, reference, provenance = case_inputs(CASE)
    record = json.loads((baseline / "inference.json").read_text())
    if reference is not None or record.get("status") != "inference_complete":
        raise ValueError("requires completed real recording inference without note reference")
    if record.get("case_id") != CASE or not record.get("model_version", "").startswith(
        "basic-pitch-"
    ):
        raise ValueError("wrong case or model")
    if (
        record.get("source_sha256") != file_sha256(wav)
        or record.get("source_provenance") != provenance
    ):
        raise ValueError("source provenance mismatch")
    for name, field in (("normalized.wav", "input_sha256"), ("raw.mid", "midi_sha256")):
        actual = file_sha256(baseline / name)
        if actual != record.get(field) or actual != record.get("artifacts_sha256", {}).get(name):
            raise ValueError(f"artifact mismatch: {name}")
    raw = read_midi(baseline / "raw.mid")
    if len(raw) != record.get("raw_note_count"):
        raise ValueError("raw event count mismatch")
    return record, raw


def run(output: Path, baseline: Path | None = None) -> dict:
    baseline = baseline or BATCH_ROOT / CASE / "basic-pitch"
    record, raw = verify(baseline)
    output.mkdir(parents=True, exist_ok=False)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        audio, rate = sf.read(baseline / "normalized.wav")
        if audio.ndim != 1 or rate != 22050:
            raise ValueError("expected mono 22050 Hz normalized audio")
        events = [
            NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], 0) for n in raw
        ]
        rows = [
            {"input_index": i, "event": raw[i], "measurement": measure(audio, rate, e, events)}
            for i, e in enumerate(events)
        ]
        report = {
            "case_id": CASE,
            "production_eligible": False,
            "actual_applied_deletions": 0,
            "reference_note_labels": None,
            "accuracy": None,
            "false_deletion_rate": None,
            "limitation": "coverage only; no per-note truth; zero selection is not proof of safety",
            "source_provenance": record["source_provenance"],
            "input_hashes": {
                name: file_sha256(baseline / name)
                for name in ("inference.json", "normalized.wav", "raw.mid")
            },
            "code_hashes": {
                name: file_sha256(ROOT / name)
                for name in (
                    "scripts/run_real_partial_probe.py",
                    "scripts/polyphony_partial_probe.py",
                    "app/pipeline/crossing_attack_evidence.py",
                    "scripts/piano_comparison_cases.py",
                    "scripts/compare_piano_model_outputs.py",
                )
            },
            "thresholds": {"max_error": MAX_ERROR, "min_tracks": MIN_TRACKS},
            "event_count": len(rows),
            "events": rows,
            "event_status_counts": dict(Counter(r["measurement"]["status"] for r in rows)),
            "track_status_counts": dict(
                Counter(t["status"] for r in rows for t in r["measurement"]["tracks"])
            ),
            "continuous_hypothesis_indices": [
                r["input_index"] for r in rows if r["measurement"]["continuous_hypothesis"]
            ],
        }
        (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        status.write_text('{"status":"complete","production_eligible":false}')
        print(
            json.dumps(
                {
                    k: report[k]
                    for k in ("event_count", "event_status_counts", "continuous_hypothesis_indices")
                }
            )
        )
        return report
    except Exception as error:
        status.write_text(
            json.dumps({"status": "failed", "production_eligible": False, "error": str(error)})
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
