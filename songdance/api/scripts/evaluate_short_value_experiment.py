import json
import resource
import sys
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory
from time import perf_counter

import librosa
import pretty_midi
import soundfile as sf

from app.pipeline.quality import evaluate_note_events
from app.pipeline.transcribe import MODEL_VERSION, NoteEvent, load_model, transcribe_audio
from scripts.generate_short_value_set import MANIFEST_PATH, OUTPUT_DIR, generate_short_value_set

REPORT_PATH = MANIFEST_PATH.parent / "short-value-ab.json"
HALF_SPEED_RATE = 0.5
Transcriber = Callable[[Path], tuple[list[NoteEvent], pretty_midi.PrettyMIDI]]


def evaluate(transcriber: Transcriber = transcribe_audio) -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not all((OUTPUT_DIR / f"{case['id']}.wav").is_file() for case in manifest["cases"]):
        generate_short_value_set()
    if transcriber is transcribe_audio:
        load_model()
        transcriber(OUTPUT_DIR / f"{manifest['cases'][0]['id']}.wav")
    results = []
    with TemporaryDirectory(prefix="songdance-half-speed-") as raw:
        workdir = Path(raw)
        for case in manifest["cases"]:
            case_id = str(case["id"])
            source = OUTPUT_DIR / f"{case_id}.wav"
            reference = _read_reference(OUTPUT_DIR / f"{case_id}.mid")
            baseline = _run_variant(source, reference, transcriber=transcriber)
            slowed = workdir / f"{case_id}-half-speed.wav"
            _time_stretch(source, slowed, HALF_SPEED_RATE)
            candidate = _run_variant(
                slowed,
                reference,
                transcriber=transcriber,
                restore_time_scale=HALF_SPEED_RATE,
            )
            results.append(
                {
                    "id": case_id,
                    "note_value": case["note_value"],
                    "reference_note_count": len(reference),
                    "original_speed": baseline,
                    "half_speed": candidate,
                }
            )
    comparison = build_comparison(results)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "experiment": "pitch_preserving_half_speed_basic_pitch",
        "model_version": MODEL_VERSION,
        "time_stretch_rate": HALF_SPEED_RATE,
        "production_path_changed": False,
        "human_readability": {
            "status": "pending",
            "rating": None,
            "reason": "HUMAN_SHORT_VALUE_REVIEW_REQUIRED",
        },
        "comparison": comparison,
        "results": results,
    }
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def _run_variant(
    audio_path: Path,
    reference: list[NoteEvent],
    *,
    transcriber: Transcriber,
    restore_time_scale: float = 1.0,
) -> dict[str, object]:
    started = perf_counter()
    events, _midi = transcriber(audio_path)
    elapsed_ms = round((perf_counter() - started) * 1_000)
    restored = rescale_events(events, restore_time_scale)
    return {
        "elapsed_ms": elapsed_ms,
        "process_peak_memory_mb": _process_peak_memory_mb(),
        "metrics": evaluate_note_events(restored, reference),
        "events": [asdict(event) for event in restored],
    }


def rescale_events(events: list[NoteEvent], factor: float) -> list[NoteEvent]:
    if factor <= 0:
        raise ValueError("time scale factor must be positive")
    return [
        replace(
            event,
            start_sec=round(event.start_sec * factor, 6),
            end_sec=round(event.end_sec * factor, 6),
        )
        for event in events
    ]


def build_comparison(results: list[dict[str, object]]) -> dict[str, object]:
    original = _aggregate(results, "original_speed")
    half_speed = _aggregate(results, "half_speed")
    deltas = {
        metric: round(half_speed[metric] - original[metric], 6)
        for metric in ("precision", "recall", "f1")
    }
    machine_gate = (
        deltas["recall"] > 0
        and deltas["f1"] > 0
        and deltas["precision"] >= -0.01
        and half_speed["p95_elapsed_ms"] <= original["p95_elapsed_ms"] * 2.5
    )
    reasons = []
    if not machine_gate:
        reasons.append("MACHINE_METRIC_GATE_FAILED")
    reasons.append("HUMAN_READABILITY_PENDING")
    return {
        "original_speed": original,
        "half_speed": half_speed,
        "metric_deltas": deltas,
        "machine_gate_passed": machine_gate,
        "production_eligible": False,
        "blocking_reasons": reasons,
    }


def _aggregate(results: list[dict[str, object]], variant: str) -> dict[str, float]:
    runs = [item[variant] for item in results]
    metrics = [run["metrics"] for run in runs]
    latencies = sorted(float(run["elapsed_ms"]) for run in runs)
    return {
        metric: round(mean(float(item[metric]) for item in metrics), 6)
        for metric in ("precision", "recall", "f1")
    } | {
        "p95_elapsed_ms": round(_percentile(latencies, 0.95), 3),
        "peak_memory_mb": round(
            max(float(run["process_peak_memory_mb"]) for run in runs), 3
        ),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * percentile
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _read_reference(path: Path) -> list[NoteEvent]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return sorted(
        (
            NoteEvent(note.start, note.end, note.pitch, note.velocity, 1.0)
            for instrument in midi.instruments
            for note in instrument.notes
        ),
        key=lambda event: (event.start_sec, event.pitch, event.end_sec),
    )


def _time_stretch(source: Path, destination: Path, rate: float) -> None:
    audio, sample_rate = librosa.load(source, sr=None, mono=True)
    stretched = librosa.effects.time_stretch(audio, rate=rate)
    sf.write(destination, stretched, sample_rate, subtype="PCM_16")


def _process_peak_memory_mb() -> float:
    value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    divisor = 1024**2 if sys.platform == "darwin" else 1024
    return round(value / divisor, 3)


if __name__ == "__main__":
    outcome = evaluate()
    raise SystemExit(0 if outcome["comparison"]["production_eligible"] else 2)
