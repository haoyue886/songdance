"""Paired whole-output renderer comparisons with identical context padding."""

import argparse
import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256

CASES = ("06-sustain", "07-soft", "14-hand-crossing")


def run(python: Path, model_source: Path, output: Path):
    output.mkdir(exist_ok=False, parents=True)
    font = Path(pretty_midi.__file__).parent / "TimGM6mb.sf2"
    runner = ROOT / "experiments/models/transkun/run_cpu.py"
    manifest = runner.parent / "source_manifest.json"
    plan = {
        "cases": CASES,
        "production_eligible": False,
        "soundfont_sha256": file_sha256(font),
        "script_sha256": file_sha256(Path(__file__)),
        "metric_sha256": file_sha256(ROOT / "scripts/compare_piano_model_outputs.py"),
        "mapping_sha256": file_sha256(ROOT / "scripts/evaluate_device_context_shift.py"),
        "preprocessor_sha256": file_sha256(ROOT / "app/pipeline/audio.py"),
        "limitation": "same alternative soundfont across cases; not real performance",
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2))
    env = dict(
        os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2"
    )
    results = []
    for case in CASES:
        midi = ROOT / f"tests/fixtures/audio/generated/{case}.mid"
        original = ROOT / f"tests/fixtures/audio/generated/{case}.wav"
        for variant in ("original", "soundfont"):
            folder = output / case / variant
            folder.mkdir(parents=True)
            status = folder / "status.json"
            status.write_text('{"status":"running"}')
            try:
                source = original
                command = None
                if variant == "soundfont":
                    command = [
                        "fluidsynth",
                        "-ni",
                        "-R",
                        "0",
                        "-C",
                        "0",
                        "-g",
                        ".2",
                        "-r",
                        "22050",
                        "-T",
                        "wav",
                        "-O",
                        "float",
                        "-F",
                        str(folder / "render.wav"),
                        str(font),
                        str(midi),
                    ]
                    with (folder / "render.log").open("x") as log:
                        subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT)
                    audio, rate = sf.read(folder / "render.wav", always_2d=True)
                    if rate != 22050 or len(audio) < 30 * rate:
                        raise ValueError("invalid render duration/rate")
                    mono = audio[: 30 * rate].mean(axis=1)
                    peak = float(np.max(np.abs(mono)))
                    if peak == 0:
                        raise ValueError("silent render")
                    source = folder / "source.wav"
                    sf.write(source, mono * (0.82 / peak), rate, subtype="PCM_16")
                preprocess_audio(source, folder / "normalized.wav")
                normalized, rate = sf.read(folder / "normalized.wav", dtype="int16")
                if normalized.ndim != 1 or rate != 22050 or len(normalized) != 30 * rate:
                    raise ValueError("invalid normalized source")
                padded = folder / "padded.wav"
                sf.write(
                    padded,
                    np.concatenate(
                        (np.zeros(rate, dtype="int16"), normalized, np.zeros(rate, dtype="int16"))
                    ),
                    rate,
                    subtype="PCM_16",
                )
                restored, _ = sf.read(padded, dtype="int16")
                if not np.array_equal(restored[rate:-rate], normalized):
                    raise ValueError("padding changed samples")
                with (folder / "inference.log").open("x") as log:
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
                    raise ValueError("model receipt mismatch")
                events, clipped, rejected = restore(read_midi(raw), 1, 30)
                original_notes = read_midi(midi)
                reference = list({(n["start_sec"], n["pitch"]): n for n in original_notes}.values())
                row = {
                    "case_id": case,
                    "variant": variant,
                    "production_eligible": False,
                    "render_command": command,
                    "source_sha256": file_sha256(source),
                    "reference_sha256": file_sha256(midi),
                    "source_midi_count": len(original_notes),
                    "distinct_reference_count": len(reference),
                    "artifacts": {p.name: file_sha256(p) for p in folder.glob("*.wav")},
                    "receipt_sha256": file_sha256(folder / "transkun/inference.json"),
                    "events": events,
                    "clipped": clipped,
                    "rejected": rejected,
                    "metrics": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
                }
                (folder / "evaluation.json").write_text(json.dumps(row, indent=2, allow_nan=False))
                status.write_text('{"status":"complete"}')
                results.append(row)
                metric = row["metrics"]["0.05"]
                print(
                    case,
                    variant,
                    {k: metric[k] for k in ["matched_count", "extra_count", "missing_count"]},
                    flush=True,
                )
            except Exception as error:
                status.write_text(json.dumps({"status": "failed", "error": str(error)}))
                raise
    (output / "summary.json").write_text(json.dumps({"plan": plan, "results": results}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--model-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=BATCH_ROOT / "soundfont-cross-cases-v1")
    args = parser.parse_args()
    run(args.python, args.model_source, args.output)
