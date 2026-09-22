"""Freeze identical normalized input and freshly rerun the Basic Pitch raw baseline."""

import argparse
import json
import time
from pathlib import Path

from app.pipeline.artifacts import write_raw_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.transcribe import MODEL_VERSION, transcribe_audio, write_raw_midi
from scripts.piano_comparison_cases import (
    BATCH_ROOT,
    CASE_IDS,
    DEFAULT_CASE,
    ROOT,
    case_inputs,
    file_sha256,
)

DEFAULT_OUTPUT = BATCH_ROOT / DEFAULT_CASE / "basic-pitch"


def run(output: Path | None = None, case_id: str = DEFAULT_CASE) -> dict:
    output = output if output is not None else BATCH_ROOT / case_id / "basic-pitch"
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("baseline output must be empty")
    receipt = output / "inference.json"
    receipt.write_text(json.dumps({"status": "running", "production_eligible": False}) + "\n")
    try:
        return _run_baseline(output, case_id)
    except Exception as error:
        receipt.write_text(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "production_eligible": False,
                },
                indent=2,
            )
            + "\n"
        )
        raise


def _run_baseline(output: Path, case_id: str) -> dict:
    source_wav, source_midi, provenance = case_inputs(case_id)
    normalized = output / "normalized.wav"
    preprocess_audio(source_wav, normalized)
    started = time.perf_counter()
    events, midi = transcribe_audio(normalized)
    elapsed = time.perf_counter() - started
    write_raw_timeline(events, output / "raw-timeline.json")
    write_raw_midi(midi, output / "raw.mid")
    report = {
        "status": "inference_complete",
        "model_version": MODEL_VERSION,
        "case_id": case_id,
        "source_provenance": provenance,
        "case_selector_sha256": file_sha256(ROOT / "scripts/piano_comparison_cases.py"),
        "source_sha256": file_sha256(source_wav),
        "source_midi_sha256": file_sha256(source_midi) if source_midi else None,
        "input_sha256": file_sha256(normalized),
        "raw_note_count": len(events),
        "midi_sha256": file_sha256(output / "raw.mid"),
        "inference_including_model_load_seconds": elapsed,
        "adapter_sha256": file_sha256(Path(__file__)),
        "transcriber_sha256": file_sha256(ROOT / "app/pipeline/transcribe.py"),
        "preprocessor_sha256": file_sha256(ROOT / "app/pipeline/audio.py"),
        "artifacts_sha256": {
            name: file_sha256(output / name)
            for name in ("normalized.wav", "raw-timeline.json", "raw.mid")
        },
        "production_eligible": False,
    }
    (output / "inference.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case-id", choices=CASE_IDS, default=DEFAULT_CASE)
    args = parser.parse_args()
    run(args.output, args.case_id)
