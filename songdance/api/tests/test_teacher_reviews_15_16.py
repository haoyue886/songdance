import json
from copy import deepcopy

import numpy as np
import pytest
import soundfile as sf

from scripts import audit_teacher_reviews_15_16 as audit
from scripts.piano_comparison_cases import file_sha256


@pytest.fixture(scope="module")
def report():
    return audit.analyze()


def test_real_sources_reproduce_and_repeated_attacks_are_counted_separately(report):
    repeated = report["cases"][0]
    source = repeated["source"]
    assert repeated["source_reconstruction"]["pcm_samples_equal"] is True
    assert source["first_eight_pitches"] == [60, 60, 62, 62, 64, 64, 67, 67]
    assert source["source_pitch_class_sequence_matches_feedback"] is True
    assert source["onset_interval_seconds"] == 0.25
    assert source["eighth_note_quarter_bpm"] == 120
    assert source["complete_eight_note_cycles"] == 14
    assert source["remaining_notes"] == 6
    for tolerance in ("0.05", "0.1"):
        metrics = repeated["raw"]["metrics_onsets_only"][tolerance]
        assert metrics["reference_count"] == metrics["matched_count"] == 118
        assert metrics["missing_count"] == 0
        assert metrics["extra_count"] == 119


def test_source_voicing_conflict_is_not_labeled_model_missed_chords(report):
    polyphony = report["cases"][1]
    source = polyphony["source"]
    assert source["source_event_count"] == 120
    assert source["source_left_event_count"] == source["source_right_event_count"] == 60
    assert source["first_three_source_chords"] == [
        [48, 55, 60, 64],
        [41, 57, 60, 65],
        [43, 55, 59, 62],
    ]
    assert source["left_chord_cardinalities"] == [4]
    assert source["right_pitch_class_sequence_matches_feedback"] is True
    assert source["chords_with_different_pitch_class_multiplicity"] == 15
    equivalence = source["teacher_notation_equivalence"]
    assert equivalence["meter"] == "2/4" and equivalence["quarter_bpm"] == 60
    assert equivalence["phrase_measures"] == 3 and equivalence["applied"] is False
    assert polyphony["status"] == "source_reconciliation_required"
    assert polyphony["raw"]["metrics_onsets_only"]["0.1"]["matched_count"] == 120
    assert polyphony["raw"]["metrics_onsets_only"]["0.1"]["extra_count"] == 29
    # Same-key note_off behavior must not be mistaken for a shorter waveform source note.
    discrepancies = polyphony["source_midi_duration_discrepancies"]
    assert len(discrepancies) == 9
    assert all(
        round(x["generated_event"]["end_sec"] - x["generated_event"]["start_sec"], 3) == 2.8
        for x in discrepancies
    )
    assert all(
        round(x["parsed_event"]["end_sec"] - x["parsed_event"]["start_sec"], 3) == 0.8
        for x in discrepancies
    )


def test_contract_contains_teacher_constraints_without_new_ratings_or_claimed_export_identity(
    report,
):
    contract = json.loads(audit.CONTRACT.read_text())
    assert report["feedback_sha256"] == file_sha256(audit.CONTRACT)
    assert report["production_eligible"] is False and report["applied_note_changes"] == 0
    assert all(r["formal_rating"] is None for r in contract["cases"])
    assert all(r["teacher_export_identity"] == "not_confirmed" for r in report["cases"])
    teacher = contract["cases"][0]["teacher"]
    assert teacher["tempo_assessment"] == "accepted_in_reviewed_score"
    assert teacher["exact_bpm"] is None
    assert teacher["hand_by_phrase_slot"] == ["left"] * 4 + ["right"] * 4


@pytest.mark.parametrize("mutation", ("pitch", "timing"))
def test_source_diagnosis_detects_changes_instead_of_always_reporting_conflict(mutation):
    teacher = json.loads(audit.CONTRACT.read_text())["cases"][1]["teacher"]
    pitches = [[55, 60, 64], [57, 60, 65], [55, 59, 62]]
    right = [72, 74, 76, 79, 76, 74, 72, 74, 76, 79, 76, 74]
    notes = [
        {"start_sec": i * 2.0, "end_sec": i * 2.0 + 2, "pitch": p, "velocity": 80}
        for i, group in enumerate(pitches)
        for p in group
    ]
    notes += [
        {"start_sec": i * 0.5, "end_sec": i * 0.5 + 0.5, "pitch": p, "velocity": 80}
        for i, p in enumerate(right)
    ]
    assert audit.describe_source("16-noisy-polyphony", notes, teacher)["source_conflict"] is False
    changed = deepcopy(notes)
    if mutation == "pitch":
        changed[0]["pitch"] = 54
    else:
        changed[0]["end_sec"] += 1
    assert audit.describe_source("16-noisy-polyphony", changed, teacher)["source_conflict"] is True


def test_wrong_audio_is_not_explained_using_generator_truth(tmp_path):
    (tmp_path / "manifest.json").write_bytes((audit.FIXTURES / "manifest.json").read_bytes())
    wav = tmp_path / "wrong.wav"
    sf.write(wav, np.zeros(22050), 22050, subtype="PCM_16")
    with pytest.raises(ValueError, match="does not reproduce"):
        audit.source_events(tmp_path, "15-repeated-notes", wav)


@pytest.mark.parametrize(
    "mutation,reason",
    (("path", "escaped"), ("hash", "changed"), ("missing", "incomplete"), ("duplicate", "exactly")),
)
def test_wrong_baseline_binding_fails_before_diagnosis(mutation, reason):
    contract = json.loads(audit.CONTRACT.read_text())
    item = contract["cases"][0]["local_bindings"]["source_wav"]
    if mutation == "path":
        item["path"] = "../outside.wav"
    elif mutation == "hash":
        item["sha256"] = "changed"
    elif mutation == "missing":
        del contract["cases"][0]["local_bindings"]["source_midi"]
    else:
        contract["cases"].append(contract["cases"][0])
    with pytest.raises(ValueError, match=reason):
        audit.verify_inputs(audit.FIXTURES, contract)


def test_exclusive_output_and_official_ratings_unchanged(tmp_path):
    originals = [audit.FIXTURES / "structure-review.json", audit.FIXTURES / "human-review.json"]
    hashes = [file_sha256(p) for p in originals]
    destination = tmp_path / "intake"
    result = audit.run(destination)
    assert json.loads((destination / "audit.json").read_text()) == result
    assert [file_sha256(p) for p in originals] == hashes
    with pytest.raises(ValueError, match="output exists"):
        audit.run(destination)
