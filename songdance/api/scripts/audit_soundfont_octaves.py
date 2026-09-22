"""Falsify octave deletion using complete paired model outputs; no production edits."""

import json
from pathlib import Path

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


def octave_candidates(events, tolerance=0.05):
    return [
        index
        for index, high in enumerate(events)
        if any(
            low["pitch"] == high["pitch"] - 12
            and abs(low["start_sec"] - high["start_sec"]) <= tolerance
            for low in events
        )
    ]


def audit(report, reference):
    events = report["events"]
    before = note_metrics(reference, events, 0.05)
    selected = set(octave_candidates(events))
    matched = {pair["estimated_index"] for pair in before["matches"]}
    after = note_metrics(
        reference, [event for i, event in enumerate(events) if i not in selected], 0.05
    )
    extra_relations = []
    for extra in before["unmatched_estimated_notes"]:
        simultaneous = [n for n in reference if abs(n["start_sec"] - extra["start_sec"]) <= 0.05]
        extra_relations.append(
            {
                "extra": extra,
                "simultaneous_reference_pitches": [n["pitch"] for n in simultaneous],
                "intervals_above_reference": [extra["pitch"] - n["pitch"] for n in simultaneous],
            }
        )
    return {
        "case_id": report["case_id"],
        "variant": report["variant"],
        "production_eligible": False,
        "purpose": "offline_rule_falsification",
        "selected_events": [events[i] for i in sorted(selected)],
        "selected_count": len(selected),
        "matched_events_removed": len(selected & matched),
        "matched_count_loss": before["matched_count"] - after["matched_count"],
        "extra_count_reduction": before["extra_count"] - after["extra_count"],
        "before": before,
        "after_hypothetical_deletion": after,
        "extra_relations": extra_relations,
        "rule_status": "rejected_false_deletion"
        if after["matched_count"] < before["matched_count"]
        else "not_validated_for_production",
    }


def run():
    root = BATCH_ROOT / "soundfont-cross-cases-v1"
    rows = []
    for case in ("06-sustain", "07-soft", "14-hand-crossing"):
        source = ROOT / f"tests/fixtures/audio/generated/{case}.mid"
        notes = read_midi(source)
        reference = list({(n["start_sec"], n["pitch"]): n for n in notes}.values())
        for variant in ("original", "soundfont"):
            path = root / case / variant / "evaluation.json"
            report = json.loads(path.read_text())
            if report["reference_sha256"] != file_sha256(source):
                raise ValueError("reference changed")
            raw = path.parent / "transkun/raw.mid"
            receipt = json.loads((raw.parent / "inference.json").read_text())
            if receipt["midi_sha256"] != file_sha256(raw):
                raise ValueError("raw model output changed")
            row = audit(report, reference)
            row["input_sha256"] = file_sha256(path)
            row["reference_sha256"] = file_sha256(source)
            rows.append(row)
            print(
                case,
                variant,
                "selected",
                row["selected_count"],
                "true loss",
                row["matched_count_loss"],
                "extras removed",
                row["extra_count_reduction"],
            )
    result = {
        "production_eligible": False,
        "actual_deleted_notes": 0,
        "trials": rows,
        "script_sha256": file_sha256(Path(__file__)),
        "conclusion": "reject global octave deletion"
        if any(r["matched_count_loss"] for r in rows)
        else "insufficient evidence",
    }
    with (root / "octave-rule-audit.json").open("x") as handle:
        json.dump(result, handle, indent=2)


if __name__ == "__main__":
    run()
