"""Whole-output evaluation of the alternative renderer; reference never fills notes."""

import json
from pathlib import Path

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def evaluate():
    root = BATCH_ROOT / "10-device/soundfont-control"
    inputs = json.loads((root / "input.json").read_text())
    for name, digest in inputs["artifacts"].items():
        if file_sha256(root / name) != digest:
            raise ValueError("control audio changed")
    receipt = json.loads((root / "transkun/inference.json").read_text())
    if (
        receipt["status"] != "inference_complete"
        or receipt["input_sha256"] != file_sha256(root / "padded.wav")
        or receipt["midi_sha256"] != file_sha256(root / "transkun/raw.mid")
    ):
        raise ValueError("inference mismatch")
    reference = ROOT / "tests/fixtures/audio/generated/10-device.mid"
    if file_sha256(reference) != inputs["source_midi_sha256"]:
        raise ValueError("reference changed")
    events, clipped, rejected = restore(read_midi(root / "transkun/raw.mid"), 1, 30)
    result = {
        "production_eligible": False,
        "input_sha256": file_sha256(root / "input.json"),
        "receipt_sha256": file_sha256(root / "transkun/inference.json"),
        "evaluator_sha256": file_sha256(Path(__file__)),
        "mapping_sha256": file_sha256(ROOT / "scripts/evaluate_device_context_shift.py"),
        "metrics": {str(t): note_metrics(read_midi(reference), events, t) for t in (0.05, 0.1)},
        "events": events,
        "clipped": clipped,
        "rejected": rejected,
        "limitation": "different rendered source, not a repaired original recording",
    }
    with (root / "evaluation.json").open("x") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    for t, m in result["metrics"].items():
        print(
            t,
            {k: m[k] for k in ["estimated_count", "matched_count", "extra_count", "missing_count"]},
        )
    print("misses", result["metrics"]["0.05"]["missing_reference_notes"])


if __name__ == "__main__":
    evaluate()
