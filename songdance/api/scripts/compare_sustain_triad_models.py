"""Raw paired inference on the new three-note fixture, never a repair of old audio."""

import argparse
import json
import os
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from app.pipeline.transcribe import MODEL_VERSION, transcribe_audio, write_raw_midi
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import ROOT, file_sha256

SOURCE = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-source-v1"


def run(output: Path, python: Path, model_source: Path):
    source_receipt = json.loads((SOURCE / "source-receipt.json").read_text())
    for name, digest in source_receipt["artifacts"].items():
        if file_sha256(SOURCE / name) != digest:
            raise ValueError("three-note fixture changed")
    output.mkdir(exist_ok=False, parents=True)
    status = output / "status.json"
    status.write_text('{"status":"running","production_eligible":false}')
    try:
        preprocess_audio(SOURCE / "source.wav", output / "normalized.wav")
        audio, rate = sf.read(output / "normalized.wav", dtype="int16")
        if audio.ndim != 1 or rate != 22050 or len(audio) != 30 * rate:
            raise ValueError("unexpected input shape")
        padded = output / "padded.wav"
        sf.write(
            padded,
            np.concatenate((np.zeros(rate, dtype="int16"), audio, np.zeros(rate, dtype="int16"))),
            rate,
            subtype="PCM_16",
        )
        events, midi = transcribe_audio(padded)
        write_raw_midi(midi, output / "basic-raw.mid")
        basic_raw = [asdict(event) for event in events]
        (output / "basic-raw.json").write_text(json.dumps(basic_raw, indent=2))
        runner = ROOT / "experiments/models/transkun/run_cpu.py"
        manifest = runner.parent / "source_manifest.json"
        env = dict(
            os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2"
        )
        with (output / "transkun.log").open("x") as log:
            subprocess.run(
                [
                    str(python),
                    str(runner),
                    "--source-root",
                    str(model_source),
                    "--manifest",
                    str(manifest),
                    "--audio",
                    str(padded),
                    "--output",
                    str(output / "transkun"),
                ],
                env=env,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        receipt_path = output / "transkun/inference.json"
        receipt = json.loads(receipt_path.read_text())
        transkun_path = output / "transkun/raw.mid"
        if (
            receipt["status"] != "inference_complete"
            or receipt["input_sha256"] != file_sha256(padded)
            or receipt["midi_sha256"] != file_sha256(transkun_path)
            or receipt["adapter_sha256"] != file_sha256(runner)
            or receipt["manifest_sha256"] != file_sha256(manifest)
        ):
            raise ValueError("Transkun receipt mismatch")
        reference = read_midi(SOURCE / "reference.mid")
        result = {
            "production_eligible": False,
            "source_kind": source_receipt["source_kind"],
            "source_receipt_sha256": file_sha256(SOURCE / "source-receipt.json"),
            "reference_sha256": file_sha256(SOURCE / "reference.mid"),
            "input_sha256": file_sha256(padded),
            "basic_model_version": MODEL_VERSION,
            "transkun_receipt_sha256": file_sha256(receipt_path),
            "script_sha256": file_sha256(Path(__file__)),
            "dependencies_sha256": {
                name: file_sha256(ROOT / name)
                for name in (
                    "app/pipeline/audio.py",
                    "app/pipeline/transcribe.py",
                    "scripts/evaluate_device_context_shift.py",
                    "scripts/compare_piano_model_outputs.py",
                )
            },
            "artifacts_sha256": {
                name: file_sha256(output / name)
                for name in ("normalized.wav", "padded.wav", "basic-raw.mid", "basic-raw.json")
            },
            "models": {},
        }
        for model, raw in [("basic", basic_raw), ("transkun", read_midi(transkun_path))]:
            mapped, clipped, rejected = restore(raw, 1, 30)
            result["models"][model] = {
                "events": mapped,
                "clipped": clipped,
                "rejected": rejected,
                "metrics": {str(t): note_metrics(reference, mapped, t) for t in (0.05, 0.1)},
            }
        (output / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False))
        status.write_text('{"status":"complete","production_eligible":false}')
        return result
    except Exception as error:
        status.write_text(
            json.dumps({"status": "failed", "error": str(error), "production_eligible": False})
        )
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--model-source", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output, args.python, args.model_source)
    for model, row in result["models"].items():
        print(
            model,
            {
                t: {k: m[k] for k in ("matched_count", "extra_count", "missing_count", "f1")}
                for t, m in row["metrics"].items()
            },
        )
