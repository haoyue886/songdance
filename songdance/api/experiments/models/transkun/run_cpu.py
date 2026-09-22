"""Run pinned Transkun in an isolated environment; the API environment needs no torch."""

import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source_root: Path, manifest_path: Path, audio_path: Path, output: Path) -> None:
    if output.exists() and any(output.iterdir()):
        raise ValueError("use an empty output directory; previous inference must remain intact")
    output.mkdir(parents=True, exist_ok=True)
    receipt = output / "inference.json"
    receipt.write_text(json.dumps({"status": "running", "production_eligible": False}) + "\n")
    try:
        _run_verified(source_root, manifest_path, audio_path, output)
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


def _run_verified(source_root: Path, manifest_path: Path, audio_path: Path, output: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    for relative, digest in manifest["source_files_sha256"].items():
        path = (source_root / relative).resolve()
        if not path.is_relative_to(source_root.resolve()) or sha256(path) != digest:
            raise ValueError(f"source fingerprint mismatch: {relative}")
    weight = source_root / "transkun/pretrained/2.0.pt"
    config = source_root / "transkun/pretrained/2.0.conf"
    if sha256(weight) != manifest["weight_sha256"] or sha256(config) != manifest["config_sha256"]:
        raise ValueError("model weight/config fingerprint mismatch")
    # Verified upstream imports are isolated from the application runtime.
    sys.path.insert(0, str(source_root.resolve()))
    import soundfile as sf
    import soxr
    import torch
    from transkun.Data import writeMidi
    from transkun.ModelTransformer import ModelConfig, TransKun

    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    started = time.perf_counter()
    settings = json.loads(config.read_text())["Model"]
    if settings["module"] != "transkun.ModelTransformer":
        raise ValueError("unexpected upstream model architecture")
    model_config = ModelConfig()
    for name, value in settings["config"].items():
        if not hasattr(model_config, name):
            raise ValueError(f"unrecognized model setting: {name}")
        setattr(model_config, name, value)
    checkpoint = torch.load(weight, map_location="cpu", weights_only=True)
    model = TransKun(conf=model_config).to("cpu")
    state = checkpoint.get("best_state_dict", checkpoint.get("state_dict"))
    if state is None:
        raise ValueError("checkpoint does not contain model parameters")
    model.load_state_dict(state, strict=True)
    model.eval()
    audio, rate = sf.read(audio_path, dtype="float32", always_2d=True)
    if audio.shape[1] != 1:
        raise ValueError("comparison input must already be normalized mono WAV")
    input_frames = len(audio)
    if rate != model.fs:
        audio = soxr.resample(audio, rate, model.fs)
    loaded = time.perf_counter()
    with torch.no_grad():
        notes = model.transcribe(torch.from_numpy(audio), discardSecondHalf=False)
    inference_done = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    midi_path = output / "raw.mid"
    writeMidi(notes).write(str(midi_path))
    result = {
        "status": "inference_complete",
        "model": "Transkun V2 No Pedal Extension",
        "source_commit": manifest["source_commit"],
        "weight_sha256": sha256(weight),
        "config_sha256": sha256(config),
        "manifest_sha256": sha256(manifest_path),
        "adapter_sha256": sha256(Path(__file__)),
        "input_sha256": sha256(audio_path),
        "input_rate": rate,
        "input_frames": input_frames,
        "model_rate": model.fs,
        "model_frames": len(audio),
        "device": "cpu",
        "segment_seconds": model.segmentSizeInSecond,
        "hop_seconds": model.segmentHopSizeInSecond,
        "load_seconds": round(loaded - started, 6),
        "inference_seconds": round(inference_done - loaded, 6),
        "midi_sha256": sha256(midi_path),
        "raw_note_count": len(notes),
        "production_eligible": False,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in (
                "torch",
                "torchaudio",
                "numpy",
                "scipy",
                "pretty_midi",
                "mir_eval",
                "soundfile",
                "soxr",
            )
        },
    }
    (output / "inference.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source_root, args.manifest, args.audio, args.output)
