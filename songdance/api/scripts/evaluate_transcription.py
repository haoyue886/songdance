import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pretty_midi

from app.pipeline.analysis import analyze_audio
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.quality import dependency_versions, evaluate_note_events
from app.pipeline.score import build_score, read_musicxml_structure, write_musicxml
from app.pipeline.transcribe import MODEL_VERSION, NoteEvent, transcribe_audio
from app.settings import Settings
from scripts.generate_regression_set import MANIFEST_PATH, OUTPUT_DIR, generate_regression_set
from scripts.human_quality_gate import compute_suite_fingerprint, file_sha256
from scripts.score_parser_validation import validate_external_parsers

RESULT_PATH = MANIFEST_PATH.parent / "regression-results.json"
HUMAN_REVIEW_PATH = MANIFEST_PATH.parent / "human-review.json"


def evaluate(settings: Settings | None = None) -> dict:
    active_settings = settings or Settings()
    cleanup_config = active_settings.note_cleanup_config
    analysis_config = active_settings.structure_analysis_config
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not all((OUTPUT_DIR / f"{case['id']}.wav").is_file() for case in manifest["cases"]):
        generate_regression_set()

    results = []
    musicxml_paths: dict[str, Path] = {}
    with TemporaryDirectory(prefix="songdance-regression-") as raw:
        workdir = Path(raw)
        for case in manifest["cases"]:
            case_id = case["id"]
            normalized = workdir / f"{case_id}.wav"
            preprocess_audio(OUTPUT_DIR / f"{case_id}.wav", normalized)
            estimated, _raw_midi = transcribe_audio(normalized)
            reference = read_reference(OUTPUT_DIR / f"{case_id}.mid")
            reference_events = [
                NoteEvent(start, end, pitch, 100, 1.0) for start, end, pitch in reference
            ]
            cleanup_result = clean_note_events(estimated, cleanup_config)
            cleaned = cleanup_result.events
            structure_analysis = analyze_audio(normalized, analysis_config)
            raw_metrics = evaluate_note_events(estimated, reference_events)
            metrics = evaluate_note_events(cleaned, reference_events)
            musicxml_status = "passed"
            structure: dict[str, object] = {}
            try:
                scored = build_score(
                    cleaned, title=case_id, analysis=structure_analysis
                )
                musicxml_path = workdir / f"{case_id}.musicxml"
                write_musicxml(scored, musicxml_path)
                structure = read_musicxml_structure(musicxml_path)
                musicxml_paths[case_id] = musicxml_path
            except Exception as error:
                musicxml_status = "failed"
                structure = {"errors": [type(error).__name__]}
            matched = int(metrics["matched_note_count"])
            corrections = len(reference) + len(cleaned) - 2 * matched
            rating = classify(corrections, float(metrics["f1"]))
            result = {
                "id": case_id,
                "description": case["description"],
                "reference_notes": len(reference),
                "raw_estimated_notes": len(estimated),
                "estimated_notes": len(cleaned),
                "matched_notes": matched,
                "corrections": corrections,
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "f1": metrics["f1"],
                "overlap": metrics["overlap"],
                "mean_onset_error_ms": metrics["mean_onset_error_ms"],
                "mean_pitch_error_semitones": metrics["mean_pitch_error_semitones"],
                "raw_metrics": raw_metrics,
                "cleanup": cleanup_result.summary(),
                "analysis": structure_analysis.summary(),
                "cleanup_recall_delta": round(
                    float(metrics["recall"]) - float(raw_metrics["recall"]), 6
                ),
                "human_rating": {"status": "not_evaluated", "rating": None},
                "musicxml_parse": {"status": musicxml_status},
                "parser_validation": {
                    "music21": {"status": musicxml_status},
                    "osmd": {"status": "pending"},
                    "xmllint": {"status": "pending"},
                },
                "reconstruction": scored.reconstruction
                if musicxml_status == "passed"
                else {
                    "status": "failed",
                    "fallback_used": False,
                    "error_code": "MUSICXML_GENERATION_FAILED",
                },
                "structure": structure,
                "rating": rating,
            }
            results.append(result)
            print(
                f"{case_id}: {rating}, F1={float(metrics['f1']):.3f}, corrections={corrections}"
            )

        external_results = validate_external_parsers(list(musicxml_paths.values()))
        for result in results:
            case_id = result["id"]
            if case_id not in musicxml_paths:
                result["parser_validation"]["osmd"] = {"status": "failed"}
                result["parser_validation"]["xmllint"] = {"status": "failed"}
                continue
            result["parser_validation"].update(
                external_results[str(musicxml_paths[case_id].resolve())]
            )

    usable = sum(item["rating"] in {"direct_use", "minor_edits"} for item in results)
    machine_summary = {
        metric: round(sum(float(item[metric]) for item in results) / len(results), 6)
        for metric in ("precision", "recall", "f1")
    }
    machine_summary["structure_error_count"] = sum(
        len(item["structure"]["errors"]) for item in results
    )
    machine_summary["raw_recall"] = round(
        sum(float(item["raw_metrics"]["recall"]) for item in results) / len(results), 6
    )
    machine_summary["cleanup_recall_delta"] = round(
        float(machine_summary["recall"]) - float(machine_summary["raw_recall"]), 6
    )
    machine_summary["analysis_fallback_count"] = sum(
        item["analysis"]["status"] != "analyzed" for item in results
    )
    machine_summary["parser_failure_count"] = sum(
        parser["status"] != "passed"
        for item in results
        for parser in item["parser_validation"].values()
    )
    machine_summary["reconstruction_fallback_count"] = sum(
        item["reconstruction"]["fallback_used"] for item in results
    )
    cleanup_gate_passed = all(
        float(item["cleanup_recall_delta"]) >= -0.05 for item in results
    )
    summary: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": MODEL_VERSION,
        "dependencies": dependency_versions(),
        "evaluation": "Automated note matching on synthesized audio; not the product quality gate",
        "product_quality_gate": False,
        "automated_usable_count": usable,
        "total_count": len(results),
        "automated_passed": usable >= 7 and cleanup_gate_passed,
        "cleanup_gate": {
            "status": "passed" if cleanup_gate_passed else "failed",
            "minimum_recall_delta": -0.05,
        },
        "evaluation_set_id": evaluation_set_id(manifest),
        "machine_summary": machine_summary,
        "threshold": "At most 10 unmatched notes and F1 >= 0.75",
        "human_evaluation": human_evaluation(),
        "results": results,
    }
    summary["evaluation_id"] = evaluation_id(summary)
    summary["comparison"] = compare_evaluations(summary)
    RESULT_PATH.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def read_reference(path: Path) -> list[tuple[float, float, int]]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return sorted(
        (note.start, note.end, note.pitch)
        for instrument in midi.instruments
        for note in instrument.notes
    )


def human_evaluation() -> dict[str, object]:
    review = json.loads(HUMAN_REVIEW_PATH.read_text(encoding="utf-8"))
    if review.get("suite_fingerprint") != compute_suite_fingerprint():
        return {
            "status": "not_evaluated",
            "reason": "STALE_SUITE_FINGERPRINT",
            "rating_counts": {},
        }
    ratings = [item.get("rating") for item in review.get("results", [])]
    if not ratings or "pending" in ratings:
        return {"status": "not_evaluated", "reason": "HUMAN_REVIEW_PENDING", "rating_counts": {}}
    rating_counts = {
        rating: ratings.count(rating)
        for rating in ("direct_use", "minor_edits", "needs_redo")
    }
    return {
        "status": "evaluated",
        "suite_type": "real_piano_human_quality_gate",
        "total_count": len(ratings),
        "usable_count": rating_counts["direct_use"] + rating_counts["minor_edits"],
        "rating_counts": rating_counts,
    }


def evaluation_id(report: dict[str, object]) -> str:
    stable = {
        key: value
        for key, value in report.items()
        if key not in {"generated_at", "evaluation_id", "comparison"}
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def evaluation_set_id(
    manifest: dict[str, object], output_dir: Path = OUTPUT_DIR
) -> str:
    cases = manifest["cases"]
    if not isinstance(cases, list):
        raise ValueError("evaluation manifest cases must be a list")
    case_fingerprints = [
        {
            "id": case["id"],
            "audio_sha256": file_sha256(output_dir / f"{case['id']}.wav"),
            "reference_midi_sha256": file_sha256(output_dir / f"{case['id']}.mid"),
        }
        for case in cases
    ]
    return evaluation_id({"manifest": manifest, "cases": case_fingerprints})


def compare_evaluations(
    baseline: dict[str, object], candidate: dict[str, object] | None = None
) -> dict[str, object]:
    if candidate is None:
        return {
            "status": "not_evaluated",
            "reason": "CANDIDATE_REPORT_UNAVAILABLE",
            "baseline_evaluation_id": evaluation_id(baseline),
            "candidate_evaluation_id": None,
        }
    if baseline.get("evaluation_set_id") != candidate.get("evaluation_set_id"):
        return {
            "status": "not_evaluated",
            "reason": "EVALUATION_SET_MISMATCH",
            "baseline_evaluation_id": evaluation_id(baseline),
            "candidate_evaluation_id": evaluation_id(candidate),
        }
    baseline_machine = baseline["machine_summary"]
    candidate_machine = candidate["machine_summary"]
    if not isinstance(baseline_machine, dict) or not isinstance(candidate_machine, dict):
        raise ValueError("machine summaries must be objects")
    metric_deltas = {
        metric: round(float(candidate_machine[metric]) - float(baseline_machine[metric]), 6)
        for metric in ("precision", "recall", "f1", "structure_error_count")
    }
    return {
        "status": "evaluated",
        "baseline_evaluation_id": evaluation_id(baseline),
        "candidate_evaluation_id": evaluation_id(candidate),
        "automated_usable_delta": int(candidate["automated_usable_count"])
        - int(baseline["automated_usable_count"]),
        "machine_metric_deltas": metric_deltas,
        "human_usable_delta": _human_usable_delta(baseline, candidate),
    }


def _human_usable_delta(
    baseline: dict[str, object], candidate: dict[str, object]
) -> int | None:
    left = baseline.get("human_evaluation")
    right = candidate.get("human_evaluation")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return None
    if left.get("status") != "evaluated" or right.get("status") != "evaluated":
        return None
    return int(right["usable_count"]) - int(left["usable_count"])


def classify(corrections: int, f1: float) -> str:
    if corrections <= 3 and f1 >= 0.9:
        return "direct_use"
    if corrections <= 10 and f1 >= 0.75:
        return "minor_edits"
    return "needs_redo"


if __name__ == "__main__":
    outcome = evaluate()
    raise SystemExit(0 if outcome["automated_passed"] else 1)
