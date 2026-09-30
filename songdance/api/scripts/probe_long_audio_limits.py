"""Probe current upload limits with temporary silence; never a music quality test.

Run from api/: python -m scripts.probe_long_audio_limits
The JSON report goes to stdout. No production data, configuration or fixtures are changed.
"""

import argparse
import ast
import hashlib
import json
import re
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.audio_validation import (
    MAX_AUDIO_BYTES,
    AudioValidationError,
    validate_audio_file,
    validate_clip,
)
from app.settings import Settings

API_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = API_ROOT.parent


def _integer_match(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    if match is None:
        raise ValueError("Frontend encoding contract changed; inspect it before probing")
    return int(match.group(1).replace("_", ""))


def frontend_encoding() -> tuple[int, int, int]:
    text = (PROJECT_ROOT / "web/src/lib/audio/clip-file.ts").read_text(encoding="utf-8")
    sample_rate = _integer_match(text, r"const OUTPUT_SAMPLE_RATE = ([\d_]+);")
    channels = _integer_match(text, r"view\.setUint16\(22, (\d+), true\)")
    bits = _integer_match(text, r"view\.setUint16\(34, (\d+), true\)")
    if (sample_rate, channels, bits) != (44_100, 1, 16):
        raise ValueError("Probe only supports the inspected 44.1 kHz mono PCM16 contract")
    return sample_rate, channels, bits


def analysis_window_seconds() -> float:
    """Read a declared default without importing the model or running analysis."""
    tree = ast.parse((API_ROOT / "app/pipeline/analysis.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AnalysisConfig":
            for field in node.body:
                if (
                    isinstance(field, ast.AnnAssign)
                    and isinstance(field.target, ast.Name)
                    and field.target.id == "max_duration_seconds"
                    and field.value is not None
                ):
                    value = ast.literal_eval(field.value)
                    if isinstance(value, (int, float)) and 0 < value <= 600:
                        return float(value)
    raise ValueError("Cannot establish the current analysis duration default")


def source_fingerprints() -> dict[str, str]:
    paths = (
        "web/src/lib/audio/clip-file.ts",
        "api/app/services/audio_validation.py",
        "api/app/settings.py",
        "api/app/pipeline/analysis.py",
        "api/scripts/probe_long_audio_limits.py",
    )
    return {name: hashlib.sha256((PROJECT_ROOT / name).read_bytes()).hexdigest() for name in paths}


def probe(durations: list[int]) -> dict[str, object]:
    if not durations or len(durations) > 12:
        raise ValueError("Provide between 1 and 12 probe durations")
    if any(type(seconds) is not int or not 1 <= seconds <= 600 for seconds in durations):
        raise ValueError("Each duration must be an integer between 1 and 600 seconds")
    rate, channels, bits = frontend_encoding()
    window = analysis_window_seconds()
    # Read the declared baseline, not a user's .env or production secrets.
    request_limit = Settings.model_fields["max_request_bytes"].default
    if type(request_limit) is not int or request_limit <= 0:
        raise ValueError("Cannot establish the current request-body default")
    results: list[dict[str, object]] = []
    with TemporaryDirectory(prefix="songdance-long-audio-probe-") as directory:
        audio_path = Path(directory) / "transport-only.wav"
        for seconds in durations:
            with wave.open(str(audio_path), "wb") as audio:
                audio.setparams((channels, bits // 8, rate, 0, "NONE", "not compressed"))
                block = bytes(rate * channels * (bits // 8))
                for _ in range(seconds):
                    audio.writeframesraw(block)
            decoded = validate_audio_file(audio_path, audio_path.name, "audio/wav")
            clip_error = None
            try:
                validate_clip(0, decoded.duration, decoded.duration)
            except AudioValidationError as error:
                clip_error = error.code
            size = audio_path.stat().st_size
            results.append(
                {
                    "requested_seconds": seconds,
                    "decoded_seconds": decoded.duration,
                    "wav_bytes": size,
                    "file_limit_allows": size <= MAX_AUDIO_BYTES,
                    "file_alone_fits_request_body": size <= request_limit,
                    "multipart_overhead_included": False,
                    "clip_validation_error": clip_error,
                    "analysis_window_covers_duration": decoded.duration <= window,
                }
            )
            audio_path.unlink()
    return {
        "schema_version": 1,
        "scope": "local_transport_and_declared_limits_only",
        "sample_kind": "generated_silence_not_quality_fixture",
        "production_ready": False,
        "browser_upload_tested": False,
        "model_inference_tested": False,
        "human_quality_tested": False,
        "limits": {
            "file_bytes": MAX_AUDIO_BYTES,
            "declared_request_body_bytes": request_limit,
            "declared_analysis_seconds": window,
        },
        "source_sha256": source_fingerprints(),
        "cases": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--durations", nargs="+", type=int, default=[30, 90, 180, 300, 600])
    args = parser.parse_args()
    try:
        report = probe(args.durations)
    except (ValueError, OSError, AudioValidationError) as error:
        # No exception payloads or local paths in diagnostics.
        print(json.dumps({"probe_completed": False, "error_type": type(error).__name__}))
        raise SystemExit(2) from None
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
