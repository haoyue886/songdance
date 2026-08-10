import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from app.pipeline.analysis import StructureAnalysis, analyze_audio
from app.settings import Settings
from scripts.generate_regression_set import MANIFEST_PATH, OUTPUT_DIR, generate_regression_set

RESULT_PATH = MANIFEST_PATH.parent / "structure-results.json"
EXPECTED_BPM = 120.0
EXPECTED_METERS = {"waltz_34": "3/4", "compound_68": "6/8"}


def evaluate(settings: Settings | None = None) -> dict[str, object]:
    active_settings = settings or Settings()
    config = active_settings.structure_analysis_config
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not all((OUTPUT_DIR / f"{case['id']}.wav").is_file() for case in manifest["cases"]):
        generate_regression_set()

    results = []
    for case in manifest["cases"]:
        source = OUTPUT_DIR / f"{case['id']}.wav"
        first = analyze_audio(source, config)
        second = analyze_audio(source, config)
        expected_meter = EXPECTED_METERS.get(case["pattern"], "4/4")
        result = {
            "id": case["id"],
            "pattern": case["pattern"],
            "expected_bpm": EXPECTED_BPM,
            "bpm": first.bpm,
            "bpm_confidence": first.bpm_confidence,
            "bpm_error": _octave_aware_bpm_error(first.bpm, EXPECTED_BPM),
            "beat_alignment_error_ms": _beat_alignment_error_ms(first),
            "downbeat_alignment_error_ms": _downbeat_alignment_error_ms(
                first, expected_meter
            ),
            "expected_time_signature": expected_meter,
            "time_signature": first.time_signature,
            "time_signature_confidence": first.time_signature_confidence,
            "time_signature_source": first.time_signature_source,
            "time_signature_correct": first.time_signature == expected_meter,
            "key_signature": first.key_signature,
            "key_confidence": first.key_confidence,
            "key_signature_source": first.key_signature_source,
            "elapsed_seconds": first.elapsed_seconds,
            "stable": _stable_payload(first) == _stable_payload(second),
            "analysis": first.summary(),
        }
        results.append(result)
        print(
            f"{case['id']}: BPM={first.bpm:.2f}, meter={first.time_signature}, "
            f"key={first.key_signature}, elapsed={first.elapsed_seconds:.3f}s"
        )

    latencies = [float(item["elapsed_seconds"]) for item in results]
    bpm_errors = [float(item["bpm_error"]) for item in results]
    bpm_accuracy = sum(error <= 5 for error in bpm_errors) / len(bpm_errors)
    meter_accuracy = sum(bool(item["time_signature_correct"]) for item in results) / len(results)
    p95 = float(np.percentile(latencies, 95, method="higher"))
    required_meter_cases = all(
        item["time_signature_correct"]
        for item in results
        if item["pattern"] in EXPECTED_METERS
    )
    required_downbeat_cases = all(
        float(item["downbeat_alignment_error_ms"]) <= 100
        for item in results
        if item["pattern"] in EXPECTED_METERS
    )
    mean_downbeat_error = float(
        np.mean([item["downbeat_alignment_error_ms"] for item in results])
    )
    gate = {
        "status": "passed"
        if (
            p95 <= 15
            and all(bool(item["stable"]) for item in results)
            and required_meter_cases
            and required_downbeat_cases
            and meter_accuracy >= 0.75
            and bpm_accuracy >= 0.75
            and float(np.median(bpm_errors)) <= 5
            and mean_downbeat_error <= 250
        )
        else "failed",
        "maximum_p95_seconds": 15,
        "minimum_meter_accuracy": 0.75,
        "minimum_bpm_accuracy": 0.75,
        "maximum_median_bpm_error": 5,
        "maximum_critical_downbeat_error_ms": 100,
        "maximum_mean_downbeat_error_ms": 250,
    }
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "analysis_version": config.version,
        "evaluation_set_id": _evaluation_set_id(manifest),
        "total_count": len(results),
        "summary": {
            "p95_elapsed_seconds": round(p95, 6),
            "median_bpm_error": round(float(np.median(bpm_errors)), 6),
            "bpm_accuracy_within_5": round(bpm_accuracy, 6),
            "mean_beat_alignment_error_ms": round(
                float(np.mean([item["beat_alignment_error_ms"] for item in results])), 6
            ),
            "mean_downbeat_alignment_error_ms": round(mean_downbeat_error, 6),
            "time_signature_accuracy": round(meter_accuracy, 6),
            "stable_count": sum(bool(item["stable"]) for item in results),
            "defaulted_meter_count": sum(
                item["time_signature_source"] == "default" for item in results
            ),
            "defaulted_key_count": sum(
                item["key_signature_source"] == "default" for item in results
            ),
        },
        "gate": gate,
        "results": results,
    }
    report["evaluation_id"] = _fingerprint(
        {key: value for key, value in report.items() if key != "generated_at"}
    )
    RESULT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def _octave_aware_bpm_error(actual: float, expected: float) -> float:
    return round(min(abs(actual * factor - expected) for factor in (0.5, 1.0, 2.0)), 6)


def _beat_alignment_error_ms(analysis: StructureAnalysis) -> float:
    if not analysis.beat_grid_seconds:
        return 500.0
    reference = np.arange(0, 30, 60 / EXPECTED_BPM)
    errors = [
        min(abs(beat - expected) for expected in reference)
        for beat in analysis.beat_grid_seconds
    ]
    return round(1_000 * float(np.mean(errors)), 6)


def _downbeat_alignment_error_ms(
    analysis: StructureAnalysis, expected_meter: str
) -> float:
    if not analysis.downbeat_grid_seconds:
        return 2_000.0
    measure_quarters = {"3/4": 3, "4/4": 4, "6/8": 3}[expected_meter]
    reference = np.arange(0, 30, measure_quarters * 60 / EXPECTED_BPM)
    errors = [
        min(abs(downbeat - expected) for expected in reference)
        for downbeat in analysis.downbeat_grid_seconds
    ]
    return round(1_000 * float(np.mean(errors)), 6)


def _stable_payload(analysis: StructureAnalysis) -> dict[str, object]:
    payload = analysis.summary()
    payload.pop("elapsed_seconds", None)
    return payload


def _evaluation_set_id(manifest: dict[str, object]) -> str:
    files = [
        {"id": case["id"], "sha256": _file_sha256(OUTPUT_DIR / f"{case['id']}.wav")}
        for case in manifest["cases"]
    ]
    return _fingerprint({"manifest": manifest, "files": files})


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


if __name__ == "__main__":
    outcome = evaluate()
    raise SystemExit(0 if outcome["gate"]["status"] == "passed" else 1)
