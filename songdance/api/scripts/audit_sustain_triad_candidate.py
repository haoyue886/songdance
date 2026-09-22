import json
import math
from dataclasses import asdict
from pathlib import Path

import pretty_midi

from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import HarmonicEvidenceConfig, extract_harmonic_evidence
from app.pipeline.quality import evaluate_note_events
from app.pipeline.transcribe import NoteEvent

ROOT = Path(__file__).parents[1]
CANDIDATE = ROOT / "tests/fixtures/audio/candidates/sustain-triad-v2"
CONTRACT = ROOT / "tests/fixtures/audio/sustain-triad-v2-manifest.json"
MATCH_TOLERANCE_SECONDS = 0.12


def audit() -> dict[str, object]:
    manifest = _read_json(CONTRACT)
    contract = manifest["case"]
    truth = _truth_events(CANDIDATE / "truth.mid")
    raw = [NoteEvent(**item) for item in _read_json(CANDIDATE / "raw-events.json")]
    matched, extra = _partition_events(raw, truth)
    comparisons = {
        "default": _evaluate_strategy(raw, truth, HarmonicEvidenceConfig()),
        "candidate_bass_priority": _evaluate_strategy(
            raw,
            truth,
            HarmonicEvidenceConfig(
                bass_priority_enabled=True,
                bass_priority_source="confirmed_sustain_triad_v2",
            ),
        ),
        "candidate_velocity_0_60": _evaluate_strategy(
            raw,
            truth,
            HarmonicEvidenceConfig(
                bass_priority_enabled=True,
                bass_priority_source="triad_candidate_parameter_scan",
                bass_maximum_velocity_ratio=0.60,
            ),
        ),
    }
    comparisons["candidate_bass_priority"].update(
        production_eligible=False,
        blocking_reasons=["NO_IMPROVEMENT_OVER_DEFAULT"],
    )
    comparisons["candidate_velocity_0_60"].update(
        production_eligible=False,
        blocking_reasons=["REAL_BASS_OCTAVE_FALSE_REMOVAL"],
    )
    matched_events = [_matched_summary(item, comparisons) for item in matched]
    extra_events = [_extra_summary(event, truth, comparisons) for event in extra]
    result = {
        "status": "audited",
        "contract_status": manifest["status"],
        "candidate_id": contract["id"],
        "truth_note_count": len(truth),
        "raw_note_count": len(raw),
        "matched_truth_count": len(matched),
        "extra_event_count": len(extra),
        "accounted_event_count": len(matched) + len(extra),
        "classification_counts": {
            kind: sum(item["classification"] == kind for item in extra_events)
            for kind in (
                "harmonic_relation_hypothesis",
                "tail_redetection_hypothesis",
                "unclassified",
            )
        },
        "matched_events": matched_events,
        "extra_events": extra_events,
        "strategy_comparison": comparisons,
        "production_change": False,
    }
    (CANDIDATE / "triad-audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "candidate_id",
                    "truth_note_count",
                    "raw_note_count",
                    "matched_truth_count",
                    "extra_event_count",
                    "accounted_event_count",
                    "classification_counts",
                )
            },
            ensure_ascii=False,
        )
    )
    return result


def _partition_events(
    raw: list[NoteEvent], truth: list[NoteEvent]
) -> tuple[list[dict[str, object]], list[NoteEvent]]:
    unused = set(range(len(raw)))
    matched = []
    for reference in sorted(truth, key=_event_key):
        candidates = [
            index
            for index in unused
            if raw[index].pitch == reference.pitch
            and abs(raw[index].start_sec - reference.start_sec) <= MATCH_TOLERANCE_SECONDS
        ]
        if not candidates:
            continue
        winner = min(
            candidates,
            key=lambda index: (
                abs(raw[index].start_sec - reference.start_sec),
                abs(raw[index].end_sec - reference.end_sec),
            ),
        )
        unused.remove(winner)
        matched.append(
            {
                "truth": reference,
                "raw": raw[winner],
                "candidate_count": len(candidates),
            }
        )
    extras = [raw[index] for index in sorted(unused, key=lambda i: _event_key(raw[i]))]
    return matched, extras


def _matched_summary(
    matched: dict[str, object], comparisons: dict[str, dict[str, object]]
) -> dict[str, object]:
    truth = matched["truth"]
    raw = matched["raw"]
    if not isinstance(truth, NoteEvent) or not isinstance(raw, NoteEvent):
        raise TypeError("matched events must contain NoteEvent values")
    return {
        "truth_event": asdict(truth),
        "raw_event": asdict(raw),
        "candidate_count": matched["candidate_count"],
        "onset_error_seconds": round(raw.start_sec - truth.start_sec, 6),
        "end_error_seconds": round(raw.end_sec - truth.end_sec, 6),
        "strategy_decisions": {
            name: _strategy_decision(raw, comparison) for name, comparison in comparisons.items()
        },
    }


def _extra_summary(
    event: NoteEvent,
    truth: list[NoteEvent],
    comparisons: dict[str, dict[str, object]],
) -> dict[str, object]:
    onset_truth = [
        item for item in truth if abs(item.start_sec - event.start_sec) <= MATCH_TOLERANCE_SECONDS
    ]
    previous_same = [
        item
        for item in truth
        if item.pitch == event.pitch
        and abs(event.start_sec - item.end_sec) <= MATCH_TOLERANCE_SECONDS
    ]
    if previous_same:
        classification = "tail_redetection_hypothesis"
    elif any(_harmonic_relation(base.pitch, event.pitch) for base in onset_truth):
        classification = "harmonic_relation_hypothesis"
    else:
        classification = "unclassified"
    return {
        "event": asdict(event),
        "classification": classification,
        "classification_is_deletion_evidence": False,
        "same_onset_truth_pitches": sorted(item.pitch for item in onset_truth),
        "previous_same_pitch_truth_count": len(previous_same),
        "strategy_decisions": {
            name: _strategy_decision(event, comparison) for name, comparison in comparisons.items()
        },
    }


def _strategy_decision(event: NoteEvent, comparison: dict[str, object]) -> dict[str, object]:
    removal = next(
        (
            item
            for item in comparison["removals"]
            if item["harmonic_pitch"] == event.pitch
            and abs(item["harmonic_start_sec"] - event.start_sec) < 1e-6
            and abs(item["harmonic_end_sec"] - event.end_sec) < 1e-6
        ),
        None,
    )
    return {
        "decision": "removed" if removal is not None else "retained",
        "reason": (
            removal["reason"] if removal is not None else "INSUFFICIENT_GENERIC_DELETION_EVIDENCE"
        ),
        "measurement": removal,
    }


def _evaluate_strategy(
    raw: list[NoteEvent], truth: list[NoteEvent], config: HarmonicEvidenceConfig
) -> dict[str, object]:
    evidence = extract_harmonic_evidence(CANDIDATE / "normalized.wav", raw, config)
    cleaned = clean_note_events(raw, harmonic_evidence=evidence)
    metrics = evaluate_note_events(cleaned.events, truth)
    return {
        "config_version": config.version,
        "removed_event_count": len(evidence.removals),
        "output_event_count": len(cleaned.events),
        "matched_note_count": metrics["matched_note_count"],
        "precision": metrics["precision"],
        "recall": metrics["recall"],
        "f1": metrics["f1"],
        "removals": [item.summary() for item in evidence.removals],
    }


def _harmonic_relation(fundamental: int, candidate: int) -> bool:
    if candidate <= fundamental:
        return False
    ratio = 2 ** ((candidate - fundamental) / 12)
    harmonic = round(ratio)
    if not 2 <= harmonic <= 6:
        return False
    return abs(1200 * math.log2(ratio / harmonic)) <= 35


def _truth_events(path: Path) -> list[NoteEvent]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return sorted(
        [
            NoteEvent(note.start, note.end, note.pitch, note.velocity, 1.0)
            for instrument in midi.instruments
            for note in instrument.notes
        ],
        key=_event_key,
    )


def _event_key(event: NoteEvent) -> tuple[float, int, float]:
    return event.start_sec, event.pitch, event.end_sec


def _read_json(path: Path):
    return json.loads(path.read_text())


if __name__ == "__main__":
    audit()
