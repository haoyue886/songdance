"""Audit harmonic hypotheses without changing the frozen candidate or scoring policy."""

import json
from collections import Counter
from pathlib import Path

import pretty_midi

from app.pipeline.harmonics import HarmonicRemoval
from scripts.build_crossing_eighth_candidate import (
    OUTPUT_DIR as BASELINE,
)
from scripts.build_crossing_eighth_candidate import (
    ROOT,
    SOURCE_MIDI,
    SOURCE_WAV,
    code_hashes,
    file_sha256,
)
from scripts.crossing_harmonic_probes import STRATEGIES, measure_probe, proposed_removals

OUTPUT = ROOT / "tests/fixtures/audio/candidates/14-hand-crossing-harmonic-audit"


def audited_events(timeline: dict, raw: list[dict], truth: set) -> tuple[list[dict], dict]:
    evidence = timeline["cleanup"]["harmonic_evidence"]
    matched: set[tuple[float, int]] = set()
    categories = Counter()
    cases = []
    for retained in timeline["reconstruction"]["crossing_eighth_cleanup"]["retained"]:
        event = retained["event"]
        onset, pitch = round(retained["slot"] * 0.5, 6), event["pitch"]
        key = onset, pitch
        if key in truth and key not in matched:
            matched.add(key)
            continue
        if key in truth:
            categories["same_slot_duplicate"] += 1
            continue
        if (round(onset - 0.5, 6), pitch) in truth or (round(onset - 1, 6), pitch) in truth:
            categories["recent_tail_candidate"] += 1
            continue
        if not any(s == onset and pitch - p in (12, 19, 24, 28, 31) for s, p in truth):
            categories["other_unconfirmed"] += 1
            continue
        categories["simultaneous_harmonic_candidate"] += 1
        indices = [i for i, e in enumerate(raw) if e == event]
        if len(indices) != 1:
            raise ValueError("candidate cannot be traced to exactly one raw event")
        pairs = []
        for pair in evidence["observations"]:
            if (
                pair["harmonic_pitch"] == pitch
                and pair["harmonic_start_sec"] == event["start_sec"]
                and pair["harmonic_end_sec"] == event["end_sec"]
            ):
                parents = [
                    i
                    for i, e in enumerate(raw)
                    if e["pitch"] == pair["fundamental_pitch"]
                    and e["start_sec"] == pair["fundamental_start_sec"]
                    and e["end_sec"] == pair["fundamental_end_sec"]
                ]
                pairs.append(
                    {
                        "measurement": pair,
                        "parent_raw_indices": parents,
                        "proposed_removals": proposed_removals(HarmonicRemoval(**pair)),
                    }
                )
        onsets = [
            o
            for o in evidence["onset_observations"]
            if o["pitch"] == pitch
            and o["start_sec"] == event["start_sec"]
            and o["end_sec"] == event["end_sec"]
        ]
        cases.append(
            {
                "raw_event_index": indices[0],
                "event": event,
                "notation_start_sec": onset,
                "onset_observations": onsets,
                "harmonic_pairs": pairs,
                "decision": "retain_pending_independent_evidence",
                "reason_codes": ["HARMONIC_INTERVAL_IS_NOT_PROOF", "HYPOTHESES_NOT_APPROVED"]
                + (["EXACT_PAIR_MEASUREMENT_UNAVAILABLE"] if not pairs else []),
            }
        )
    return cases, {
        "correct_onsets": len(matched),
        "extra_events": sum(categories.values()),
        "diagnostic_categories_not_deletion_evidence": dict(categories),
    }


def run(output: Path = OUTPUT) -> dict:
    baseline_paths = [
        BASELINE / "candidate-report.json",
        BASELINE / "raw-events.json",
        BASELINE / "artifacts/timeline.json",
        SOURCE_MIDI,
        SOURCE_WAV,
    ]
    baseline_hashes = {str(p.relative_to(ROOT)): file_sha256(p) for p in baseline_paths}
    report = json.loads(baseline_paths[0].read_text())
    if report["code_sha256"] != code_hashes():
        raise ValueError("frozen candidate was produced by a different pipeline")
    if report["source_sha256"] != file_sha256(SOURCE_WAV):
        raise ValueError("source WAV does not match the frozen candidate")
    if report["source_midi_sha256"] != file_sha256(SOURCE_MIDI):
        raise ValueError("reference MIDI does not match the frozen candidate")
    for name, digest in report["artifacts_sha256"].items():
        if file_sha256(BASELINE / "artifacts" / name) != digest:
            raise ValueError(f"candidate artifact mismatch: {name}")
    timeline = json.loads(baseline_paths[2].read_text())
    raw = json.loads(baseline_paths[1].read_text())
    source = pretty_midi.PrettyMIDI(str(SOURCE_MIDI))
    truth = {
        (round(n.start, 6), n.pitch) for instrument in source.instruments for n in instrument.notes
    }
    candidates, summary = audited_events(timeline, raw, truth)
    wave_root = output / "probes"
    wave_root.mkdir(parents=True, exist_ok=True)
    probes = []
    combinations = [(0.0, 0.0)] + [
        (a, p) for a in (0.03, 0.08, 0.2) for p in (0.0, 1.5707963267948966, 3.141592653589793)
    ]
    for lower_pitch in (48, 51, 60):
        for interval in (12, 19):
            for duration in (0.14, 0.2):
                for upper_amplitude, phase in combinations:
                    path = wave_root / f"probe-{len(probes):03}.wav"
                    measured, _, _ = measure_probe(
                        path,
                        lower_pitch=lower_pitch,
                        interval=interval,
                        duration=duration,
                        upper_amplitude=upper_amplitude,
                        phase=phase,
                    )
                    probes.append(
                        {
                            "id": path.stem,
                            "wav": str(path.relative_to(output)),
                            "wav_sha256": file_sha256(path),
                            **measured,
                        }
                    )
    strategies = {}
    for name in STRATEGIES:
        false_deletions = [
            p["id"]
            for p in probes
            if p["truth"] == "real_simultaneous_note" and p["proposed_removals"][name]
        ]
        true_deletions = [
            p["id"]
            for p in probes
            if p["truth"] == "natural_partial_only" and p["proposed_removals"][name]
        ]
        selected = [
            c["raw_event_index"]
            for c in candidates
            if any(pair["proposed_removals"][name] for pair in c["harmonic_pairs"])
        ]
        strategies[name] = {
            "status": "rejected_real_note_counterexample" if false_deletions else "unapproved",
            "production_eligible": False,
            "false_deletion_ids": false_deletions,
            "natural_partial_detection_ids": true_deletions,
            "target_candidate_indices": selected,
        }
    if any(file_sha256(ROOT / name) != digest for name, digest in baseline_hashes.items()):
        raise RuntimeError("baseline changed during audit")
    payload = {
        "schema_version": 1,
        "case_id": "14-hand-crossing",
        "status": "audited_no_new_deletions",
        "production_eligible": False,
        "baseline_hashes": baseline_hashes,
        "baseline_pipeline_hashes": code_hashes(),
        "audit_code_hashes": {
            str(p.relative_to(ROOT)): file_sha256(p)
            for p in (Path(__file__), ROOT / "scripts/crossing_harmonic_probes.py")
        },
        "summary": summary,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "probe_count": len(probes),
        "probe_truth_counts": dict(Counter(p["truth"] for p in probes)),
        "probes": probes,
        "strategies": strategies,
        "hypothesis_definition": {
            "release_tracking": {
                "max_onset_delta_seconds": 0.08,
                "max_energy_ratio": 0.22,
                "max_velocity_ratio": 0.85,
                "max_duration_ratio": 1.0,
                "min_release_ratio_exclusive": 0.25,
                "min_tracking_ratio": 0.3,
                "requires_no_relative_independent_onset": True,
                "requires_unblocked_probes": True,
                "rejects_existing_energy_velocity_attack_support": True,
            },
            "strict_tracking": {
                "inherits": "release_tracking",
                "min_tracking_ratio": 0.9,
                "max_velocity_ratio": 0.6,
            },
        },
        "new_deletion_count": 0,
        "limitation": "controlled additive tones test postprocessing safety, not model accuracy",
    }
    (output / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "candidate_count": len(candidates),
                "probe_count": len(probes),
                "false_deletions": {n: len(s["false_deletion_ids"]) for n, s in strategies.items()},
                "hypothetical_candidate_deletions": {
                    n: len(s["target_candidate_indices"]) for n, s in strategies.items()
                },
                "new_deletion_count": 0,
            },
            ensure_ascii=False,
        )
    )
    return payload


if __name__ == "__main__":
    run()
