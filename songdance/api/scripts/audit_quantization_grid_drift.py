"""Measure beat-grid reconstruction drift; diagnose without retiming any score."""

import json
from pathlib import Path
from statistics import median

from scripts.piano_comparison_cases import ROOT, file_sha256


def measure(beat_times):
    if len(beat_times) < 3 or any(b <= a for a, b in zip(beat_times, beat_times[1:], strict=False)):
        raise ValueError("requires at least three increasing beat times")
    gaps = [b - a for a, b in zip(beat_times, beat_times[1:], strict=False)]
    # Match current quantize._subdivision_grid upper median exactly.
    step = sorted(gaps)[len(gaps) // 2]
    span = (beat_times[-1] - beat_times[0]) / (len(beat_times) - 1)
    return {
        "beat_count": len(beat_times),
        "current_interval": step,
        "span_average_interval": span,
        "endpoint_difference_seconds": step * (len(beat_times) - 1)
        - (beat_times[-1] - beat_times[0]),
        "median_absolute_interval_deviation": median(abs(g - span) for g in gaps),
        "suggested_automatic_change": False,
    }


def run(root):
    rows = []
    for path in sorted(root.glob("*-review-artifacts/*/timeline.json")):
        timeline = json.loads(path.read_text())
        beats = timeline["analysis"]["beat_grid_seconds"]
        if len(beats) < 3:
            continue
        rows.append(
            {
                "case_id": path.parent.name,
                "suite": path.parent.parent.name,
                "timeline_sha256": file_sha256(path),
                "detected_bpm": timeline["analysis"]["bpm"],
                "metrics": measure(beats),
            }
        )
    report = {
        "production_eligible": False,
        "score_changed": False,
        "cases": rows,
        "script_sha256": file_sha256(Path(__file__)),
        "quantizer_sha256": file_sha256(ROOT / "app/pipeline/quantize.py"),
        "limitation": "grid reconstruction discrepancy, not proof that a global mean fits rubato",
    }
    with (root / "quantization-grid-audit.json").open("x") as handle:
        json.dump(report, handle, indent=2)
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(len(run(args.directory)["cases"]))
