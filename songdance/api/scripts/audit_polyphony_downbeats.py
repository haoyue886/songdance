"""Diagnostic chord timing against an explicit meter hypothesis, not beat detection."""

import argparse
import json
from pathlib import Path
from statistics import median

from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, verify_inputs
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import file_sha256


def diagnose(events, origin=0.0, measure_seconds=2.0):
    if measure_seconds <= 0:
        raise ValueError("measure duration must be positive")
    groups = []
    for index, event in sorted(enumerate(events), key=lambda pair: pair[1]["start_sec"]):
        if event["pitch"] >= 72:
            continue
        if not groups or event["start_sec"] - groups[-1][0][1]["start_sec"] > 0.08:
            groups.append([(index, event)])
        else:
            groups[-1].append((index, event))
    candidates = []
    for group in groups:
        if len({event["pitch"] for _, event in group}) < 3:
            continue
        center = median(event["start_sec"] for _, event in group)
        number = round((center - origin) / measure_seconds)
        target = origin + number * measure_seconds
        errors = [event["start_sec"] - target for _, event in group]
        candidates.append(
            {
                "input_indices": [i for i, _ in group],
                "center_seconds": center,
                "pitches": [n["pitch"] for _, n in group],
                "nearest_measure_index": number,
                "hypothesized_downbeat_seconds": target,
                "event_timing_errors_seconds": errors,
                "near_hypothesized_downbeat": bool(max(abs(x) for x in errors) <= 0.08),
            }
        )
    centers = [c["center_seconds"] for c in candidates]
    gaps = [b - a for a, b in zip(centers, centers[1:], strict=False)]
    return {
        "candidate_count": len(candidates),
        "candidates": candidates,
        "median_chord_interval_seconds": median(gaps) if gaps else None,
        "all_adjacent_intervals_near_measure": bool(gaps)
        and all(abs(g - measure_seconds) <= 0.08 for g in gaps),
        "all_candidates_near_hypothesized_downbeat": bool(candidates)
        and all(c["near_hypothesized_downbeat"] for c in candidates),
        "configuration": {
            "bass_inspection_ceiling": 72,
            "cluster_window_seconds": 0.08,
            "origin_seconds": origin,
            "measure_seconds": measure_seconds,
            "source": "case_specific_register_and_teacher_meter_hypothesis",
        },
        "audio_downbeat_detection_verified": False,
        "actual_note_changes": 0,
    }


def run(output):
    if output.exists():
        raise ValueError("output already exists")
    paths = verify_inputs(FIXTURES, json.loads(CONTRACT.read_text()))["16-noisy-polyphony"]
    result = {
        "production_eligible": False,
        "case_id": "16-noisy-polyphony",
        "script_sha256": file_sha256(Path(__file__)),
        "feedback_sha256": file_sha256(CONTRACT),
        "inputs": {k: file_sha256(v) for k, v in paths.items()},
        "raw": diagnose(read_midi(paths["original/raw.mid"])),
        "old_score_on_teacher_grid": diagnose(read_midi(paths["original/score.mid"])),
        "latest_score_on_teacher_grid": diagnose(read_midi(paths["frozen_final/score.mid"])),
        "limitation": "comparison against proposed 2/4 at 60 BPM; not automatic meter proof",
    }
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(encoded)
    for name in ("raw", "old_score_on_teacher_grid", "latest_score_on_teacher_grid"):
        row = result[name]
        print(
            name,
            row["candidate_count"],
            row["median_chord_interval_seconds"],
            row["all_candidates_near_hypothesized_downbeat"],
        )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
