"""One-command isolated raw transcription, without notation or reference templates."""

import argparse
import json
import os
import subprocess
from pathlib import Path

import pretty_midi
import soundfile as sf

from app.pipeline.audio import preprocess_audio
from scripts.piano_comparison_cases import ROOT, file_sha256

RUNNER = ROOT / "experiments/models/transkun/run_cpu.py"
MANIFEST = RUNNER.parent / "source_manifest.json"


def read_events(path):
    midi = pretty_midi.PrettyMIDI(str(path))
    return sorted(
        [
            {
                "start_sec": n.start,
                "end_sec": n.end,
                "pitch": n.pitch,
                "velocity": n.velocity,
                "confidence": None,
                "hand": None,
                "instrument_index": i,
            }
            for i, instrument in enumerate(midi.instruments)
            for n in instrument.notes
        ],
        key=lambda n: (n["start_sec"], n["pitch"], n["end_sec"], n["instrument_index"]),
    )


def run(audio: Path, output: Path, python: Path, source_root: Path, timeout: float = 300):
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    audio = audio.resolve(strict=True)
    output.mkdir(exist_ok=False, parents=True)
    state = {
        "status": "running",
        "stage": "preprocess",
        "production_eligible": False,
        "source_sha256": file_sha256(audio),
        "runner_sha256": file_sha256(RUNNER),
        "manifest_sha256": file_sha256(MANIFEST),
        "pipeline_sha256": file_sha256(Path(__file__)),
        "preprocessor_sha256": file_sha256(ROOT / "app/pipeline/audio.py"),
    }
    status = output / "pipeline.json"

    def save():
        status.write_text(json.dumps(state, indent=2, allow_nan=False) + "\n")

    save()
    try:
        normalized = output / "normalized.wav"
        preprocess_audio(audio, normalized)
        info = sf.info(normalized)
        if info.channels != 1 or info.samplerate != 22050 or info.frames <= 0 or info.duration > 90:
            raise ValueError("requires nonempty normalized mono audio up to 90 seconds")
        if file_sha256(audio) != state["source_sha256"]:
            raise ValueError("source changed during preprocessing")
        state.update(
            stage="inference", input_sha256=file_sha256(normalized), duration_seconds=info.duration
        )
        save()
        command = [
            str(python.absolute()),
            str(RUNNER),
            "--source-root",
            str(source_root.resolve()),
            "--manifest",
            str(MANIFEST),
            "--audio",
            str(normalized.resolve()),
            "--output",
            str((output / "model").resolve()),
        ]
        env = dict(
            os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2", VECLIB_MAXIMUM_THREADS="2"
        )
        with (output / "inference.log").open("x") as log:
            subprocess.run(
                command, env=env, check=True, timeout=timeout, stdout=log, stderr=subprocess.STDOUT
            )
        state["stage"] = "export"
        save()
        receipt_path = output / "model/inference.json"
        receipt = json.loads(receipt_path.read_text())
        raw = output / "model/raw.mid"
        if (
            receipt.get("status") != "inference_complete"
            or receipt["input_sha256"] != state["input_sha256"]
            or receipt["input_sha256"] != file_sha256(normalized)
            or receipt["manifest_sha256"] != state["manifest_sha256"]
            or receipt["adapter_sha256"] != state["runner_sha256"]
            or receipt["midi_sha256"] != file_sha256(raw)
        ):
            raise ValueError("model output provenance mismatch")
        events = read_events(raw)
        if len(events) != receipt["raw_note_count"]:
            raise ValueError("MIDI count differs from inference receipt")
        timeline = output / "raw-timeline.json"
        timeline.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "model": receipt["model"],
                    "production_eligible": False,
                    "time_basis": "normalized_audio_seconds_without_padding",
                    "confidence_semantics": "not provided by MIDI; unknown, not calibrated",
                    "notes": events,
                },
                indent=2,
                allow_nan=False,
            )
            + "\n"
        )
        state.update(
            status="complete",
            stage="complete",
            raw_note_count=len(events),
            artifacts_sha256={
                str(p.relative_to(output)): file_sha256(p)
                for p in (normalized, raw, receipt_path, timeline)
            },
        )
        save()
        return state
    except Exception as error:
        state.update(status="failed", error_type=type(error).__name__, error=str(error))
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    result = run(args.audio, args.output, args.python, args.source_root, args.timeout)
    print(json.dumps({"status": result["status"], "raw_note_count": result["raw_note_count"]}))
