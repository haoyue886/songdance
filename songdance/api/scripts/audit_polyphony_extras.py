"""Audit existing audio-only rules on 16; source labels never select deletions."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.pipeline.audio import preprocess_audio
from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, source_events, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256
from scripts.polyphony_evidence_diagnostics import evidence_limits


def evaluate(events, evidence):
    if evidence.status != "available":
        raise ValueError("audio evidence unavailable")
    harmonic = [i for i, e in enumerate(events) if any(r.matches(e) for r in evidence.removals)]
    _, tail = clean_crossing_tails(events, evidence, 1.0)
    return {"harmonic": harmonic, "tail": [r["input_index"] for r in tail["removals"]]}, tail


def annotate(raw, reference, evidence, selected):
    metrics = note_metrics(reference, raw, 0.1)
    matched = {m["estimated_index"] for m in metrics["matches"]}
    rows = []
    for i, event in enumerate(raw):
        observations = [
            asdict(o)
            for o in evidence.onset_observations
            if (o.pitch, o.start_sec, o.end_sec)
            == (event["pitch"], event["start_sec"], event["end_sec"])
        ]
        covering = [
            j
            for j, n in enumerate(reference)
            if n["pitch"] == event["pitch"]
            and n["start_sec"] < event["start_sec"] - 0.1 < n["end_sec"]
            and event["start_sec"] < n["end_sec"]
        ]
        rows.append(
            {
                "input_index": i,
                "event": event,
                "label": "matched_onset" if i in matched else "unmatched_onset",
                "source_same_pitch_sounding_indices": covering,
                "onset_evidence": observations,
                "evidence_limits": evidence_limits(event, observations),
                "selected_by": [k for k, indices in selected.items() if i in indices],
            }
        )
    return (
        metrics,
        rows,
        {
            name: {
                "selected": len(indices),
                "matched_onsets_selected": len(set(indices) & matched),
                "unmatched_onsets_selected": len(set(indices) - matched),
            }
            for name, indices in selected.items()
        },
    )


def run(output: Path):
    paths = verify_inputs(FIXTURES, json.loads(CONTRACT.read_text()))["16-noisy-polyphony"]
    output.mkdir(parents=True, exist_ok=False)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        preprocess_audio(paths["source_wav"], output / "normalized.wav")
        raw = read_midi(paths["original/raw.mid"])
        events = [
            NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], 0) for n in raw
        ]
        evidence = extract_harmonic_evidence(
            output / "normalized.wav",
            events,
            include_decay_evidence=True,
            include_transient_evidence=True,
        )
        selected, tail = evaluate(events, evidence)
        # Reference is loaded only after audio-only decisions are fixed.
        reference, reproduction = source_events(FIXTURES, "16-noisy-polyphony", paths["source_wav"])
        metrics, rows, decisions = annotate(raw, reference, evidence, selected)
        report = {
            "production_eligible": False,
            "actual_applied_deletions": 0,
            "confidence_source": "zero placeholder, not calibrated probability",
            "quarter_seconds": 1.0,
            "tempo_source": "explicit 60 BPM hypothesis",
            "inputs": {k: file_sha256(v) for k, v in paths.items()},
            "source_reconstruction": reproduction,
            "metrics_onsets_only": metrics,
            "decisions": decisions,
            "tail": tail,
            "events": rows,
            "evidence": evidence.summary(),
            "label_counts": dict(Counter(r["label"] for r in rows)),
            "code_sha256": {
                str(p.relative_to(ROOT)): file_sha256(p)
                for p in sorted((ROOT / "app/pipeline").glob("*.py"))
            },
        }
        report["code_sha256"].update(
            {
                name: file_sha256(ROOT / name)
                for name in (
                    "scripts/audit_polyphony_extras.py",
                    "scripts/polyphony_evidence_diagnostics.py",
                    "scripts/audit_teacher_reviews_15_16.py",
                    "scripts/generate_regression_set.py",
                    "scripts/compare_piano_model_outputs.py",
                )
            }
        )
        (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        status.write_text('{"status":"complete","production_eligible":false}')
        print(json.dumps(decisions))
        return report
    except Exception as error:
        status.write_text(
            json.dumps({"status": "failed", "error": str(error), "production_eligible": False})
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
