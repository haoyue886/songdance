"""Check an existing conservative tail rule on repeated-note audio, without applying it."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.pipeline.audio import preprocess_audio
from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def run(output: Path):
    paths = verify_inputs(FIXTURES, json.loads(CONTRACT.read_text()))["15-repeated-notes"]
    output.mkdir(parents=True, exist_ok=False)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        preprocess_audio(paths["source_wav"], output / "normalized.wav")
        raw = read_midi(paths["original/raw.mid"])
        events = [
            NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], n["velocity"] / 127)
            for n in raw
        ]
        evidence = extract_harmonic_evidence(
            output / "normalized.wav",
            events,
            include_decay_evidence=True,
            include_transient_evidence=True,
        )
        if evidence.status != "available":
            raise ValueError("complete audio evidence unavailable")
        kept, decisions = clean_crossing_tails(events, evidence, 0.5)
        reference = read_midi(paths["source_midi"])
        report = {
            "production_eligible": False,
            "actual_applied_deletions": 0,
            "scope": "offline transfer audit; no production or score update",
            "quarter_seconds": 0.5,
            "confidence_source": "velocity placeholder, not model probability",
            "inputs": {k: file_sha256(v) for k, v in paths.items()},
            "normalized_sha256": file_sha256(output / "normalized.wav"),
            "code": {
                name: file_sha256(ROOT / name)
                for name in (
                    "scripts/audit_repeated_tails.py",
                    "app/pipeline/harmonics.py",
                    "app/pipeline/crossing_tail_cleanup.py",
                    "app/pipeline/crossing_attack_evidence.py",
                    "app/pipeline/onset_decay.py",
                    "app/pipeline/audio.py",
                )
            },
            "evidence": evidence.summary(),
            "decisions": decisions,
            "before": note_metrics(reference, raw, 0.1),
            "after_hypothetical": note_metrics(reference, [asdict(n) for n in kept], 0.1),
        }
        (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False))
        status.write_text('{"status":"complete","production_eligible":false}')
        print(
            "hypothetical removed",
            decisions["removed_count"],
            {
                k: report["after_hypothetical"][k]
                for k in ("matched_count", "extra_count", "missing_count")
            },
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
    args = parser.parse_args()
    run(args.output)
