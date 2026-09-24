"""Diagnose late teacher feedback against bound sources without editing model notes."""

import argparse
import io
import json
from collections import Counter
from pathlib import Path
from statistics import median
from xml.etree import ElementTree as ET

import numpy as np
import soundfile as sf

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.generate_regression_set import build_pattern, synthesize
from scripts.piano_comparison_cases import ROOT, file_sha256

FIXTURES = ROOT / "tests/fixtures/audio"
CONTRACT = FIXTURES / "teacher-review-15-16.json"
CASES = ("15-repeated-notes", "16-noisy-polyphony")
C_MAJOR_PITCH_CLASSES = (0, 2, 4, 5, 7, 9, 11)


def verify_inputs(root: Path, contract: dict) -> dict[str, dict[str, Path]]:
    rows = contract["cases"]
    if len(rows) != 2 or {r["case_id"] for r in rows} != set(CASES):
        raise ValueError("requires exactly the two reviewed cases")
    if contract.get("production_eligible") is not False:
        raise ValueError("feedback cannot authorize production")
    paths = {}
    for row in rows:
        required = {"source_wav", "source_midi"} | {
            f"{version}/{name}"
            for version in ("original", "frozen_final")
            for name in ("raw.mid", "score.mid", "score.musicxml", "timeline.json")
        }
        if set(row["local_bindings"]) != required:
            raise ValueError("incomplete baseline bindings")
        bindings = {}
        for name, item in row["local_bindings"].items():
            path = (root / item["path"]).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError("feedback binding escaped fixture root")
            if file_sha256(path) != item["sha256"]:
                raise ValueError(f"source/artifact changed: {row['case_id']}/{name}")
            bindings[name] = path
        paths[row["case_id"]] = bindings
    return paths


def source_events(root: Path, case_id: str, wav: Path) -> tuple[list[dict], dict]:
    manifest = json.loads((root / "manifest.json").read_text())
    index, case = next((i, c) for i, c in enumerate(manifest["cases"]) if c["id"] == case_id)
    rate, duration = manifest["sample_rate"], manifest["duration_seconds"]
    generated = build_pattern(case["pattern"])
    audio = synthesize(
        generated, duration, rate, case["noise"], case["bandwidth"] == "device", 1000 + index
    )
    encoded = io.BytesIO()
    sf.write(encoded, audio, rate, format="WAV", subtype="PCM_16")
    encoded.seek(0)
    replay, replay_rate = sf.read(encoded, dtype="int16")
    original, original_rate = sf.read(wav, dtype="int16")
    if original_rate != replay_rate or not np.array_equal(original, replay):
        raise ValueError("generator does not reproduce the bound WAV; source diagnosis withheld")
    notes = [
        {"pitch": n.pitch, "start_sec": n.start, "end_sec": n.end, "velocity": n.velocity}
        for n in generated
    ]
    notes.sort(key=lambda n: (n["start_sec"], n["pitch"], n["end_sec"]))
    return notes, {"pcm_samples_equal": True, "sample_rate": rate, "duration_seconds": duration}


def midi_duration_discrepancies(source: list[dict], parsed: list[dict]) -> list[dict]:
    matched = note_metrics(source, parsed, 0.004)
    if matched["missing_count"] or matched["extra_count"]:
        raise ValueError("source MIDI onset set differs from the waveform generator")
    return [
        {
            "generated_event": source[p["reference_index"]],
            "parsed_event": parsed[p["estimated_index"]],
        }
        for p in matched["matches"]
        if abs(source[p["reference_index"]]["end_sec"] - parsed[p["estimated_index"]]["end_sec"])
        > 0.006
    ]


def midi_diagnosis(reference: list[dict], path: Path) -> dict:
    events = read_midi(path)
    return {
        "event_count": len(events),
        "metrics_onsets_only": {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)},
        "duration_range_seconds": [
            min(n["end_sec"] - n["start_sec"] for n in events),
            max(n["end_sec"] - n["start_sec"] for n in events),
        ],
    }


def describe_source(case_id: str, notes: list[dict], teacher: dict) -> dict:
    if case_id == "15-repeated-notes":
        expected = [C_MAJOR_PITCH_CLASSES[d - 1] for d in teacher["melody_degrees"]]
        matches = all(n["pitch"] % 12 == expected[i % len(expected)] for i, n in enumerate(notes))
        interval = median(
            b["start_sec"] - a["start_sec"] for a, b in zip(notes, notes[1:], strict=False)
        )
        return {
            "source_event_count": len(notes),
            "first_eight_pitches": [n["pitch"] for n in notes[:8]],
            "onset_interval_seconds": interval,
            "eighth_note_quarter_bpm": 60 / (2 * interval),
            "complete_eight_note_cycles": len(notes) // 8,
            "remaining_notes": len(notes) % 8,
            "hand_source": "teacher slot assignment; MIDI does not encode actual hands",
            "source_pitch_class_sequence_matches_feedback": matches,
            "source_conflict": not matches,
        }
    # This split describes this generator only, never a model hand-assignment rule.
    left = [n for n in notes if n["pitch"] < 72]
    right = [n for n in notes if n["pitch"] >= 72]
    starts = sorted({n["start_sec"] for n in left})
    interval = median(b - a for a, b in zip(starts, starts[1:], strict=False))
    groups = [[n["pitch"] for n in left if n["start_sec"] == t] for t in starts]
    expected = [[C_MAJOR_PITCH_CLASSES[d - 1] for d in g] for g in teacher["left_groups_degrees"]]
    chord_mismatches = sum(
        Counter(p % 12 for p in group) != Counter(expected[i % len(expected)])
        for i, group in enumerate(groups)
    )
    right_pattern = [
        C_MAJOR_PITCH_CLASSES[d - 1] for g in teacher["right_groups_degrees"] for d in g
    ]
    right_matches = all(
        n["pitch"] % 12 == right_pattern[i % len(right_pattern)] for i, n in enumerate(right)
    )
    overlaps_next = any(n["end_sec"] - n["start_sec"] > interval + 0.006 for n in left)
    conflicts = []
    if chord_mismatches:
        conflicts.append("source_chord_voicing_differs_from_teacher_three_notes")
    if overlaps_next:
        conflicts.append("source_hold_overlaps_next_chord")
    if not right_matches:
        conflicts.append("source_right_melody_differs_from_teacher")
    return {
        "source_event_count": len(notes),
        "source_left_event_count": len(left),
        "source_right_event_count": len(right),
        "register_split_for_source_inspection_only": 72,
        "chord_onset_count": len(starts),
        "chord_interval_seconds": interval,
        "first_three_source_chords": groups[:3],
        "left_chord_cardinalities": sorted(set(map(len, groups))),
        "first_twelve_right_pitches": [n["pitch"] for n in right[:12]],
        "right_pitch_class_sequence_matches_feedback": right_matches,
        "chords_with_different_pitch_class_multiplicity": chord_mismatches,
        "left_generated_durations_seconds": sorted(
            {round(n["end_sec"] - n["start_sec"], 6) for n in left}
        ),
        "right_generated_durations_seconds": sorted(
            {round(n["end_sec"] - n["start_sec"], 6) for n in right}
        ),
        "teacher_notation_equivalence": {
            "meter": "2/4",
            "quarter_bpm": 120 / interval,
            "left_quarter_length": 2,
            "right_quarter_length": 0.5,
            "phrase_measures": 3,
            "applied": False,
        },
        "source_conflict": bool(conflicts),
        "conflicts": conflicts,
    }


def analyze(root: Path = FIXTURES, contract_path: Path = CONTRACT) -> dict:
    contract = json.loads(contract_path.read_text())
    bindings = verify_inputs(root, contract)
    verbatim = ROOT.parents[1] / contract["verbatim"]["path"]
    if file_sha256(verbatim) != contract["verbatim"]["sha256"]:
        raise ValueError("feedback text changed")
    rows = []
    for case_id in CASES:
        paths = bindings[case_id]
        notes, reproduction = source_events(root, case_id, paths["source_wav"])
        parsed_reference = read_midi(paths["source_midi"])
        feedback = next(row["teacher"] for row in contract["cases"] if row["case_id"] == case_id)
        source = describe_source(case_id, notes, feedback)
        row = {
            "case_id": case_id,
            "status": "requires_revision",
            "formal_rating": None,
            "teacher_export_identity": "not_confirmed",
            "source_reconstruction": reproduction,
            "source": source,
            "source_midi_duration_discrepancies": midi_duration_discrepancies(
                notes, parsed_reference
            ),
            "raw": midi_diagnosis(notes, paths["original/raw.mid"]),
            "scores": {},
        }
        for version in ("original", "frozen_final"):
            timeline = json.loads(paths[f"{version}/timeline.json"].read_text())
            xml = ET.parse(paths[f"{version}/score.musicxml"])
            row["scores"][version] = {
                **midi_diagnosis(notes, paths[f"{version}/score.mid"]),
                "tempo_bpm": timeline["tempo_bpm"],
                "meter": timeline["time_signature"],
                "notated_note_types": dict(
                    Counter(
                        n.findtext("type")
                        for n in xml.findall(".//note")
                        if n.find("pitch") is not None
                    )
                ),
            }
        if source["source_conflict"]:
            row["status"] = "source_reconciliation_required"
        rows.append(row)
    return {
        "schema_version": 1,
        "production_eligible": False,
        "applied_note_changes": 0,
        "feedback_sha256": file_sha256(contract_path),
        "cases": rows,
        "code_sha256": {
            name: file_sha256(ROOT / name)
            for name in (
                "scripts/generate_regression_set.py",
                "scripts/compare_piano_model_outputs.py",
                "scripts/audit_teacher_reviews_15_16.py",
            )
        },
        "limitation": "source-onset diagnosis only; reviewed export and quality remain unconfirmed",
    }


def run(output: Path, root: Path = FIXTURES, contract_path: Path = CONTRACT) -> dict:
    if output.exists():
        raise ValueError("output exists; preserve previous feedback audit")
    report = analyze(root, contract_path)
    output.mkdir(parents=True, exist_ok=False)
    (output / "audit.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    for row in report["cases"]:
        metric = row["raw"]["metrics_onsets_only"]["0.1"]
        print(
            row["case_id"],
            row["status"],
            {k: metric[k] for k in ("matched_count", "extra_count", "missing_count")},
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
