"""Fixed context sweep: report every trial, never fuse reference-selected notes."""

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256

PREFIXES = (1, 2, 6, 8)


def run(python: Path, source_root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    source = BATCH_ROOT / "10-device/basic-pitch/normalized.wav"
    audio, rate = sf.read(source, dtype="int16")
    if audio.ndim != 1:
        raise ValueError("mono input required")
    runner = ROOT / "experiments/models/transkun/run_cpu.py"
    manifest = runner.parent / "source_manifest.json"
    plan = {
        "prefixes": PREFIXES,
        "source_sha256": file_sha256(source),
        "script_sha256": file_sha256(Path(__file__)),
        "mapping_sha256": file_sha256(ROOT / "scripts/evaluate_device_context_shift.py"),
        "metric_sha256": file_sha256(ROOT / "scripts/compare_piano_model_outputs.py"),
        "production_eligible": False,
        "added_notes": 0,
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2))
    env = dict(
        os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2"
    )
    completed = []
    for prefix in PREFIXES:
        folder = output / f"prefix-{prefix}"
        folder.mkdir()
        padded = folder / "input.wav"
        sf.write(
            padded,
            np.concatenate(
                (np.zeros(prefix * rate, dtype="int16"), audio, np.zeros(rate, dtype="int16"))
            ),
            rate,
            subtype="PCM_16",
        )
        restored, read_rate = sf.read(padded, dtype="int16")
        if read_rate != rate or not np.array_equal(
            audio, restored[prefix * rate : prefix * rate + len(audio)]
        ):
            raise ValueError("original PCM samples changed")
        receipt_path = folder / "status.json"
        receipt_path.write_text(json.dumps({"status": "running", "prefix": prefix}))
        try:
            with (folder / "inference.log").open("x") as log:
                subprocess.run(
                    [
                        str(python),
                        str(runner),
                        "--source-root",
                        str(source_root),
                        "--manifest",
                        str(manifest),
                        "--audio",
                        str(padded),
                        "--output",
                        str(folder / "transkun"),
                    ],
                    env=env,
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            receipt = json.loads((folder / "transkun/inference.json").read_text())
            raw = folder / "transkun/raw.mid"
            if (
                receipt["status"] != "inference_complete"
                or receipt["input_sha256"] != file_sha256(padded)
                or receipt["midi_sha256"] != file_sha256(raw)
                or receipt["manifest_sha256"] != file_sha256(manifest)
                or receipt["adapter_sha256"] != file_sha256(runner)
            ):
                raise ValueError("inference provenance mismatch")
            events, clipped, rejected = restore(read_midi(raw), prefix, len(audio) / rate)
            # Reference is used only after inference, for whole-output evaluation.
            ref_path = ROOT / "tests/fixtures/audio/generated/10-device.mid"
            reference = read_midi(ref_path)
            row = {
                "prefix_seconds": prefix,
                "source_samples_preserved": True,
                "input_sha256": file_sha256(padded),
                "reference_sha256": file_sha256(ref_path),
                "inference_receipt_sha256": file_sha256(folder / "transkun/inference.json"),
                "events": events,
                "clipped": clipped,
                "rejected": rejected,
                "metrics": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
            }
            (folder / "evaluation.json").write_text(json.dumps(row, indent=2, allow_nan=False))
            completed.append(row)
            receipt_path.write_text(json.dumps({"status": "complete"}))
            metric = row["metrics"]["0.05"]
            print(
                prefix,
                {k: metric[k] for k in ["matched_count", "extra_count", "missing_count"]},
                flush=True,
            )
        except Exception as error:
            receipt_path.write_text(json.dumps({"status": "failed", "error": str(error)}))
            raise
    (output / "summary.json").write_text(json.dumps({"plan": plan, "trials": completed}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.python, args.source_root, args.output)
