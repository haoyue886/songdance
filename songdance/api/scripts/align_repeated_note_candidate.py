"""Isolated regular-onset timing candidate; no pitch filtering or hand inference."""

import argparse
import json
from pathlib import Path
from statistics import median

import numpy as np
import pretty_midi

from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import file_sha256


def align(events):
    ordered = sorted(enumerate(events), key=lambda item: (item[1]["start_sec"], item[1]["pitch"]))
    clusters = []
    for _, event in ordered:
        if not clusters or event["start_sec"] - clusters[-1][0] > 0.08:
            clusters.append([event["start_sec"]])
        else:
            clusters[-1].append(event["start_sec"])
    if len(clusters) < 16:
        raise ValueError("insufficient regular attacks")
    centers = np.array([median(group) for group in clusters])
    interval = median(np.diff(centers))
    if interval <= 0.16 or max(abs(np.diff(centers) - interval)) > 0.05:
        raise ValueError("irregular or unresolved attacks")
    slots = np.rint((centers - centers[0]) / interval)
    if len(set(slots)) != len(slots):
        raise ValueError("ambiguous attack slots")
    slope, intercept = np.polyfit(slots, centers, 1)
    # Keep the first observed cluster as origin, not a reference-score time.
    origin = float(centers[0])
    bpm = round(30 / float(slope))
    if not 114 <= bpm <= 126:
        raise ValueError("outside reviewed fixture tempo neighborhood")
    step = 30 / bpm
    if max(abs(centers - (origin + slots * step))) > 0.05:
        raise ValueError("fixed tempo would move attacks too far")
    result, changes, identities = [], [], set()
    for index, event in ordered:
        slot = round((event["start_sec"] - origin) / step)
        start = origin + slot * step
        if slot < 0 or abs(start - event["start_sec"]) > 0.08:
            raise ValueError("event outside timing tolerance")
        identity = (slot, event["pitch"])
        if identity in identities:
            raise ValueError("same-key slot collision; do not merge repeated attacks")
        identities.add(identity)
        after = {**event, "start_sec": start, "end_sec": start + step}
        result.append(after)
        changes.append(
            {
                "input_index": index,
                "before": event,
                "after": after,
                "slot": slot,
                "measure_index": slot // 8,
                "slot_in_measure": slot % 8,
                "onset_shift_seconds": start - event["start_sec"],
            }
        )
    return result, {
        "quarter_bpm": bpm,
        "meter": "4/4",
        "eighth_seconds": step,
        "origin_seconds": origin,
        "model_attack_cluster_count": len(clusters),
        "fitted_interval_seconds": float(slope),
        "fitted_intercept_seconds": float(intercept),
        "configuration_source": "teacher_eighth_meter_with_model_onset_grid",
        "changes": changes,
    }


def run(output):
    if output.exists():
        raise ValueError("output already exists")
    contract = json.loads(CONTRACT.read_text())
    bindings = verify_inputs(FIXTURES, contract)["15-repeated-notes"]
    raw = bindings["original/raw.mid"]
    events, timing = align(read_midi(raw))
    output.mkdir(parents=True, exist_ok=False)
    midi = pretty_midi.PrettyMIDI(initial_tempo=timing["quarter_bpm"])
    midi.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    piano = pretty_midi.Instrument(0)
    piano.notes = [
        pretty_midi.Note(
            n["velocity"],
            n["pitch"],
            n["start_sec"] - timing["origin_seconds"],
            n["end_sec"] - timing["origin_seconds"],
        )
        for n in events
    ]
    midi.instruments.append(piano)
    midi.write(str(output / "candidate.mid"))
    reference = read_midi(bindings["source_midi"])
    report = {
        "production_eligible": False,
        "status": "timing_only_harmonics_unresolved",
        "raw_sha256": file_sha256(raw),
        "feedback_sha256": file_sha256(CONTRACT),
        "script_sha256": file_sha256(Path(__file__)),
        "source_sha256": file_sha256(bindings["source_wav"]),
        "reference_sha256": file_sha256(bindings["source_midi"]),
        "midi_sha256": file_sha256(output / "candidate.mid"),
        "timing": timing,
        "midi_time_origin_seconds": timing["origin_seconds"],
        "time_mapping": "audio_seconds = midi_seconds + midi_time_origin_seconds",
        "events": events,
        "note_additions": 0,
        "note_deletions": 0,
        "hand_assignment": "not_applied_unresolved_extra_notes",
        "metrics": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
    }
    (output / "audit.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(
        {
            k: report["metrics"]["0.05"][k]
            for k in ("estimated_count", "matched_count", "extra_count", "missing_count")
        }
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
