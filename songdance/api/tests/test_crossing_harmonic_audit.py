import ast
import json
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import HarmonicRemoval, extract_harmonic_evidence
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent
from scripts.audit_crossing_harmonics import OUTPUT
from scripts.build_crossing_eighth_candidate import (
    ROOT,
    code_hashes,
    file_sha256,
)
from scripts.crossing_harmonic_probes import STRATEGIES, paired_wave, proposed_removals
from scripts.run_structure_review import _notation_context_for_case


@pytest.fixture(scope="module")
def report():
    return json.loads((OUTPUT / "report.json").read_text())


def test_audit_is_bound_to_unmodified_source_candidate_and_current_code(report):
    for field in ("baseline_hashes", "audit_code_hashes"):
        for name, digest in report[field].items():
            assert file_sha256(ROOT / name) == digest
    assert report["baseline_pipeline_hashes"] == code_hashes()
    assert report["summary"] == {
        "correct_onsets": 111,
        "extra_events": 128,
        "diagnostic_categories_not_deletion_evidence": {
            "recent_tail_candidate": 97,
            "simultaneous_harmonic_candidate": 22,
            "other_unconfirmed": 9,
        },
    }
    assert report["new_deletion_count"] == 0
    assert report["status"] == "audited_no_new_deletions"
    assert report["production_eligible"] is False


def test_all_22_candidates_are_traceable_to_raw_events_and_saved_audio_measurements(report):
    root = ROOT / "tests/fixtures/audio/candidates/14-hand-crossing-tail-v2"
    raw = json.loads((root / "raw-events.json").read_text())
    timeline = json.loads((root / "artifacts/timeline.json").read_text())
    evidence = timeline["cleanup"]["harmonic_evidence"]
    assert len(report["candidates"]) == report["candidate_count"] == 22
    assert len({c["raw_event_index"] for c in report["candidates"]}) == 22
    for candidate in report["candidates"]:
        assert candidate["event"] == raw[candidate["raw_event_index"]]
        assert candidate["decision"] == "retain_pending_independent_evidence"
        for o in candidate["onset_observations"]:
            assert o in evidence["onset_observations"]
        for pair in candidate["harmonic_pairs"]:
            measurement = pair["measurement"]
            assert measurement in evidence["observations"]
            assert len(pair["parent_raw_indices"]) == 1
            parent = raw[pair["parent_raw_indices"][0]]
            assert (parent["pitch"], parent["start_sec"], parent["end_sec"]) == (
                measurement["fundamental_pitch"],
                measurement["fundamental_start_sec"],
                measurement["fundamental_end_sec"],
            )
            assert pair["proposed_removals"] == proposed_removals(HarmonicRemoval(**measurement))


def test_120_controlled_probes_recompute_rejection_counts_from_actual_measurements(report):
    assert report["probe_count"] == len(report["probes"]) == 120
    assert report["probe_truth_counts"] == {
        "natural_partial_only": 12,
        "real_simultaneous_note": 108,
    }
    for probe in report["probes"]:
        assert file_sha256(OUTPUT / probe["wav"]) == probe["wav_sha256"]
        expected = (
            proposed_removals(HarmonicRemoval(**probe["measurement"]))
            if probe["measurement"]
            else {name: False for name in STRATEGIES}
        )
        assert probe["proposed_removals"] == expected
        assert probe["event_source"] == "postprocess_test_hypotheses_not_model_inference"
    for name, strategy in report["strategies"].items():
        wrong = [
            p["id"]
            for p in report["probes"]
            if p["truth"] == "real_simultaneous_note" and p["proposed_removals"][name]
        ]
        hits = [
            p["id"]
            for p in report["probes"]
            if p["truth"] == "natural_partial_only" and p["proposed_removals"][name]
        ]
        assert strategy["false_deletion_ids"] == wrong
        assert strategy["natural_partial_detection_ids"] == hits
        assert wrong and hits
        assert strategy["status"] == "rejected_real_note_counterexample"
        assert strategy["production_eligible"] is False


@pytest.mark.parametrize("interval", [12, 19])
@pytest.mark.parametrize("strategy", STRATEGIES)
def test_real_wav_counterexample_is_reproducible_and_official_pipeline_keeps_note(
    report, interval, strategy
):
    ids = set(report["strategies"][strategy]["false_deletion_ids"])
    probe = next(
        p for p in report["probes"] if p["id"] in ids and p["parameters"]["interval"] == interval
    )
    events = [NoteEvent(**e) for e in probe["candidate_events"]]
    evidence = extract_harmonic_evidence(OUTPUT / probe["wav"], events)
    actual_pair = next(
        p for p in (*evidence.observations, *evidence.removals) if p.matches(events[1])
    )
    assert actual_pair.summary() == probe["measurement"]
    assert proposed_removals(actual_pair)[strategy] is True
    cleaned = clean_note_events(
        events, harmonic_evidence=evidence, preserve_simultaneous_unisons=True
    )
    assert cleaned.events == events
    scored = build_score(
        cleaned.events,
        harmonic_evidence=evidence,
        notation_context=_notation_context_for_case({"texture_hint": "crossing_eighth_melody"}),
    )
    assert Counter(e.pitch for e in scored.notation_notes) == Counter(e.pitch for e in events)


def test_paired_waves_only_add_the_declared_independent_note(report):
    probe = next(
        p
        for p in report["probes"]
        if p["parameters"]["phase"] == np.pi / 2 and p["parameters"]["upper_amplitude"] == 0.08
    )
    values = probe["parameters"]
    original, rate, _ = paired_wave(**{**values, "upper_amplitude": 0})
    mixed, _, _ = paired_wave(**values)
    from_disk, disk_rate = sf.read(OUTPUT / probe["wav"])
    assert disk_rate == rate
    assert np.max(np.abs(from_disk - mixed)) < 1e-7
    # FLOAT storage and common gain retain the mix; no variant peak normalization.
    assert np.array_equal(mixed[: int(0.2 * rate)], original[: int(0.2 * rate)])
    assert not np.array_equal(mixed, original)
    assert np.max(np.abs(mixed)) < 1


def test_unapproved_hypotheses_are_not_imported_by_runtime_pipeline():
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        assert not any(name and "crossing_harmonic_probes" in name for name in imports)
