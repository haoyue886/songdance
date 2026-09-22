"""Compare raw model notes on the same frozen normalized input, without notation rules."""

import argparse
import json
from pathlib import Path

import numpy as np
import pretty_midi
from mir_eval.transcription import match_notes

from scripts.piano_comparison_cases import (
    BATCH_ROOT,
    CASE_IDS,
    DEFAULT_CASE,
    ROOT,
    case_inputs,
    file_sha256,
)

BASELINE = BATCH_ROOT / DEFAULT_CASE / "basic-pitch"
MODEL_MANIFEST = ROOT / "experiments/models/transkun/source_manifest.json"


def note_metrics(reference: list[dict], estimated: list[dict], tolerance: float) -> dict:
    def arrays(notes):
        intervals = np.array([(n["start_sec"], n["end_sec"]) for n in notes]).reshape((-1, 2))
        frequencies = np.array([440 * 2 ** ((n["pitch"] - 69) / 12) for n in notes])
        return intervals, frequencies

    pairs = match_notes(
        *arrays(reference), *arrays(estimated), onset_tolerance=tolerance, offset_ratio=None
    )
    pairs = [(int(r), int(e)) for r, e in pairs]
    correct = len(pairs)
    precision = correct / len(estimated) if estimated else 0.0
    recall = correct / len(reference) if reference else 0.0
    matched_ref, matched_est = {r for r, _ in pairs}, {e for _, e in pairs}
    return {
        "onset_tolerance_seconds": tolerance,
        "reference_count": len(reference),
        "estimated_count": len(estimated),
        "matched_count": correct,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        "extra_count": len(estimated) - correct,
        "missing_count": len(reference) - correct,
        "missing_reference_notes": [n for i, n in enumerate(reference) if i not in matched_ref],
        "unmatched_estimated_notes": [n for i, n in enumerate(estimated) if i not in matched_est],
        "matches": [
            {
                "reference_index": r,
                "estimated_index": e,
                "onset_error_seconds": estimated[e]["start_sec"] - reference[r]["start_sec"],
            }
            for r, e in pairs
        ],
    }


def read_midi(path: Path) -> list[dict]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return sorted(
        [
            {"pitch": n.pitch, "start_sec": n.start, "end_sec": n.end, "velocity": n.velocity}
            for instrument in midi.instruments
            for n in instrument.notes
        ],
        key=lambda n: (n["start_sec"], n["pitch"], n["end_sec"]),
    )


def compare(
    output: Path, destination: Path, *, case_id: str = DEFAULT_CASE, baseline: Path | None = None
) -> dict:
    baseline = (
        baseline
        if baseline is not None
        else (BASELINE if case_id == DEFAULT_CASE else BATCH_ROOT / case_id / "basic-pitch")
    )
    source_wav, source_midi, provenance = case_inputs(case_id)
    if destination.exists():
        raise ValueError("comparison report must not overwrite an existing file")
    inference = json.loads((output / "inference.json").read_text())
    source_report = json.loads((baseline / "inference.json").read_text())
    if inference["status"] != "inference_complete":
        raise ValueError("candidate inference is not complete")
    normalized = baseline / "normalized.wav"
    if source_report.get("status") != "inference_complete":
        raise ValueError("Basic Pitch inference is not complete")
    if (
        inference["input_sha256"] != file_sha256(normalized)
        or source_report["input_sha256"] != inference["input_sha256"]
    ):
        raise ValueError("models did not receive identical normalized input")
    if source_report.get("case_id") != case_id:
        raise ValueError("baseline belongs to a different case")
    if source_report.get("source_provenance") != provenance:
        raise ValueError("source provenance changed")
    if source_report["source_sha256"] != file_sha256(source_wav):
        raise ValueError("frozen source WAV changed")
    if inference["midi_sha256"] != file_sha256(output / "raw.mid"):
        raise ValueError("candidate MIDI changed after inference")
    if source_report["source_midi_sha256"] != (file_sha256(source_midi) if source_midi else None):
        raise ValueError("reference MIDI changed")
    if (
        source_report.get("case_selector_sha256")
        != file_sha256(ROOT / "scripts/piano_comparison_cases.py")
        or source_report["adapter_sha256"]
        != file_sha256(ROOT / "scripts/prepare_piano_model_input.py")
        or source_report.get("transcriber_sha256")
        != file_sha256(ROOT / "app/pipeline/transcribe.py")
        or source_report["preprocessor_sha256"] != file_sha256(ROOT / "app/pipeline/audio.py")
    ):
        raise ValueError("Basic Pitch input preparation does not match the recorded code")
    manifest = json.loads(MODEL_MANIFEST.read_text())
    if (
        inference["manifest_sha256"] != file_sha256(MODEL_MANIFEST)
        or inference["weight_sha256"] != manifest["weight_sha256"]
        or inference["source_commit"] != manifest["source_commit"]
        or inference["adapter_sha256"] != file_sha256(MODEL_MANIFEST.parent / "run_cpu.py")
    ):
        raise ValueError("candidate provenance does not match the verified model/adapter")
    for name in ("normalized.wav", "raw-timeline.json", "raw.mid"):
        if source_report["artifacts_sha256"][name] != file_sha256(baseline / name):
            raise ValueError(f"Basic Pitch artifact changed: {name}")
    raw_path = baseline / "raw-timeline.json"
    basic_payload = json.loads(raw_path.read_text())
    basic = [
        {k: n[k] for k in ("pitch", "start_sec", "end_sec", "velocity")}
        for n in basic_payload["notes"]
    ]
    original = read_midi(source_midi) if source_midi else []
    reference = list({(n["start_sec"], n["pitch"]): n for n in original}.values())
    candidate = read_midi(output / "raw.mid")
    result = {
        "status": "offline_comparison_complete",
        "production_eligible": False,
        "case_id": case_id,
        "source_kind": provenance["kind"],
        "source_provenance": provenance,
        "case_selector_sha256": file_sha256(ROOT / "scripts/piano_comparison_cases.py"),
        "source_sha256": file_sha256(source_wav),
        "normalized_sha256": file_sha256(normalized),
        "reference_sha256": (file_sha256(source_midi) if source_midi else None),
        "source_midi_count": len(original) if source_midi else None,
        "distinct_reference_count": len(reference) if source_midi else None,
        "note_convention": "same pitch/onset reference unisons counted once; onset-only evaluation",
        "basic_pitch_model": basic_payload["model_version"],
        "basic_pitch_inference": source_report,
        "transkun_inference": inference,
        "basic_pitch_raw": {str(t): note_metrics(reference, basic, t) for t in (0.05, 0.1)}
        if source_midi
        else None,
        "transkun_raw": {str(t): note_metrics(reference, candidate, t) for t in (0.05, 0.1)}
        if source_midi
        else None,
        "evaluator_sha256": file_sha256(Path(__file__)),
        "input_artifacts_sha256": {
            "basic_pitch_raw_timeline": file_sha256(raw_path),
            "basic_pitch_receipt": file_sha256(baseline / "inference.json"),
            "transkun_raw_midi": file_sha256(output / "raw.mid"),
            "transkun_receipt": file_sha256(output / "inference.json"),
        },
        "limitation": (
            "single synthetic clip; no claim about real-performance quality or publication"
        ),
    }
    if source_midi is None:
        result["note_convention"] = "no note-level reference; differences are not errors"
        result["limitation"] = "real recording without ground truth; no accuracy or winner claim"
        differences = {}
        for tolerance in (0.05, 0.1):
            aligned = note_metrics(basic, candidate, tolerance)
            differences[str(tolerance)] = {
                "basic_pitch_count": len(basic),
                "transkun_count": len(candidate),
                "shared_pitch_onset_count": aligned["matched_count"],
                "basic_pitch_only": aligned["missing_reference_notes"],
                "transkun_only": aligned["unmatched_estimated_notes"],
            }
        result["unscored_model_differences"] = differences
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with destination.open("x") as handle:
        handle.write(encoded)
    print(json.dumps({"case_id": case_id, "status": result["status"]}))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transkun-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--case-id", choices=CASE_IDS, default=DEFAULT_CASE)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    compare(args.transkun_output, args.report, case_id=args.case_id, baseline=args.baseline)
