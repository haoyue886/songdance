import json

import pretty_midi

from app.pipeline.transcribe import MODEL_VERSION
from scripts.evaluate_device_bass_ab import (
    MANIFEST_PATH,
    OUTPUT,
    _code_hashes,
    _payload_hash,
    _sha256,
)


def report() -> dict[str, object]:
    return json.loads((OUTPUT / "report.json").read_text())


def test_device_bass_manifest_is_a_complete_paired_design():
    manifest = json.loads(MANIFEST_PATH.read_text())
    variants = manifest["variants"]
    assert len(variants) == 4
    assert {(variant["bandwidth"], variant["bass_velocity"]) for variant in variants} == {
        ("full", 78),
        ("180-5500", 78),
        ("full", 38),
        ("180-5500", 38),
    }
    assert manifest["noise"] == 0.01
    assert manifest["synthesis_seed"] == 1009
    assert manifest["noise_injection_stage"] == "before_bandwidth_filter"
    assert manifest["mixing_version"] == "paired-stems-v1"
    assert manifest["production_change"] is False


def test_device_bass_report_keeps_bass_and_treble_separate():
    result = report()
    assert set(result["variants"]) == {
        "full-standard",
        "device-standard",
        "full-weak",
        "device-weak",
    }
    for variant in result["variants"].values():
        assert variant["truth_note_count"] == 90
        assert variant["raw"]["bass"]["metrics"]["reference_note_count"] == 30
        assert variant["raw"]["treble"]["metrics"]["reference_note_count"] == 60
        assert len(variant["files"]["source_wav_sha256"]) == 64
        assert len(variant["files"]["truth_midi_sha256"]) == 64
        assert (
            variant["raw"]["bass"]["metrics"]["recall"]
            == variant["cleaned"]["bass"]["metrics"]["recall"]
        )


def test_device_bass_variants_only_change_declared_factors():
    manifest = json.loads(MANIFEST_PATH.read_text())
    note_sets = {}
    velocity_sets = {}
    for variant in manifest["variants"]:
        midi = pretty_midi.PrettyMIDI(str(OUTPUT / variant["id"] / "truth.mid"))
        notes = sorted(
            [note for instrument in midi.instruments for note in instrument.notes],
            key=lambda note: (note.start, note.pitch),
        )
        note_sets[variant["id"]] = [(note.start, note.end, note.pitch) for note in notes]
        velocity_sets[variant["id"]] = {
            "bass": {note.velocity for note in notes if note.pitch <= 47},
            "treble": {note.velocity for note in notes if note.pitch >= 60},
        }
    assert len({tuple(values) for values in note_sets.values()}) == 1
    assert velocity_sets["full-standard"] == velocity_sets["device-standard"]
    assert velocity_sets["full-weak"] == velocity_sets["device-weak"]
    assert velocity_sets["full-standard"]["bass"] == {78}
    assert velocity_sets["full-weak"]["bass"] == {38}
    assert velocity_sets["full-standard"]["treble"] == velocity_sets["full-weak"]["treble"]
    source_contract = report()["source_contract"]
    assert source_contract["mixing_version"] == "paired-stems-v1"
    assert source_contract["noise_injection_stage"] == "before_bandwidth_filter"
    assert source_contract["shared_master_gain"] > 0
    for name, fingerprint in source_contract["shared_files"].items():
        assert fingerprint == _sha256(OUTPUT / "shared" / name)


def test_device_bass_report_is_bound_to_current_files_and_pipeline():
    result = report()
    assert result["model_version"] == MODEL_VERSION
    assert result["manifest_sha256"] == _sha256(MANIFEST_PATH)
    assert result["code_sha256"] == _code_hashes()
    for name, variant in result["variants"].items():
        root = OUTPUT / name
        expected = {
            "truth_midi_sha256": _sha256(root / "truth.mid"),
            "source_wav_sha256": _sha256(root / "source.wav"),
            "normalized_wav_sha256": _sha256(root / "normalized.wav"),
            "raw_events_sha256": _sha256(root / "raw-events.json"),
            "score_musicxml_sha256": _sha256(root / "score.musicxml"),
        }
        assert variant["files"] == expected


def test_device_bass_effects_are_derived_from_saved_variant_metrics():
    result = report()
    variants = result["variants"]
    recall = {name: value["raw"]["bass"]["metrics"]["recall"] for name, value in variants.items()}
    assert result["factor_effects"] == {
        "bandwidth_at_standard_velocity": round(
            recall["device-standard"] - recall["full-standard"], 6
        ),
        "bandwidth_at_weak_velocity": round(recall["device-weak"] - recall["full-weak"], 6),
        "weak_velocity_at_full_bandwidth": round(recall["full-weak"] - recall["full-standard"], 6),
        "weak_velocity_at_device_bandwidth": round(
            recall["device-weak"] - recall["device-standard"], 6
        ),
        "bandwidth_velocity_interaction": round(
            (recall["device-weak"] - recall["device-standard"])
            - (recall["full-weak"] - recall["full-standard"]),
            6,
        ),
    }
    stored_id = result.pop("evaluation_id")
    assert stored_id == _payload_hash(result)
    assert result["model_change_recommended"] is False
    assert result["production_change"] is False


def test_device_bass_result_localizes_the_observed_failure():
    result = report()
    variants = result["variants"]
    assert variants["full-standard"]["raw"]["bass"]["metrics"]["recall"] == 1.0
    assert variants["full-weak"]["raw"]["bass"]["metrics"]["recall"] == 1.0
    assert variants["device-standard"]["raw"]["bass"]["metrics"]["recall"] == 1.0
    assert variants["device-weak"]["raw"]["bass"]["metrics"]["recall"] == 0.966667
    missed = variants["device-weak"]["raw"]["bass"]["missed_truth_events"]
    assert len(missed) == 1
    assert {event["pitch"] for event in missed} == {36}
    assert {event["start_sec"] for event in missed} == {20.0}
    assert all(
        variant["raw"]["treble"]["metrics"]["recall"] == 1.0 for variant in variants.values()
    )
    assert result["conclusion_codes"] == ["BANDLIMITED_WEAK_BASS_INTERACTION"]
    assert result["conclusion_scope"] == ("synthetic_paired_end_to_end_preprocessing_experiment")
    assert all(
        variant["score_assignment"]["matched_bass_truth_count"] == 30
        for variant in variants.values()
    )


def test_device_bandwidth_reduces_measured_bass_spectrum():
    variants = report()["variants"]
    for level in ("standard", "weak"):
        full = variants[f"full-{level}"]["spectrum"]
        device = variants[f"device-{level}"]["spectrum"]
        assert device["source"]["low_40_180_rms"] < full["source"]["low_40_180_rms"]
        assert (
            device["normalized"]["low_to_treble_rms_ratio"]
            < full["normalized"]["low_to_treble_rms_ratio"]
        )
        for pitch in ("36", "41", "43"):
            assert (
                device["source"]["bass_fundamentals"][pitch]["rms"]
                < full["source"]["bass_fundamentals"][pitch]["rms"]
            )


def test_cleanup_and_score_assignment_are_reported_separately():
    variants = report()["variants"]
    for variant in variants.values():
        assert variant["cleanup"]["status"] == "applied"
        assert variant["cleanup_effect"]["bass_recall_delta"] == 0.0
        assert variant["cleanup_effect"]["newly_missed_bass_truth_events"] == []
        assignment = variant["score_assignment"]
        assert assignment["fallback_used"] is False
        assert assignment["reconstruction_status"] == "reconstructed"
        assert assignment["structure"]["errors"] == []
        assert (
            assignment["matched_bass_assigned_left_count"] == assignment["matched_bass_truth_count"]
        )
