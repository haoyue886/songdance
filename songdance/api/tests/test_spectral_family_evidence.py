import json

import numpy as np
import pytest
import soundfile as sf

from app.pipeline.transcribe import NoteEvent
from scripts.audit_crossing_harmonics import OUTPUT as PREVIOUS
from scripts.audit_crossing_spectral_family import OUTPUT
from scripts.build_crossing_eighth_candidate import ROOT, file_sha256
from scripts.crossing_harmonic_probes import paired_wave
from scripts.spectral_family_evidence import measure_spectral_family


@pytest.mark.parametrize("interval", [12, 19])
@pytest.mark.parametrize("amplitude", [0.0, 0.03, 0.2])
def test_frequency_overlap_does_not_claim_independent_note_or_authorize_deletion(
    interval, amplitude
):
    audio, rate, events = paired_wave(51, interval, amplitude, 0, 0.2)
    result = measure_spectral_family(audio, rate, events[1], events)
    assert result["status"] == "ambiguous"
    assert result["decision"] == "retain"
    assert result["independent_attack_confirmed"] is False
    assert result["partials"]
    assert all(p["compatible_modeled_partials"] for p in result["partials"])


@pytest.mark.parametrize("interval", [3, 5, 7, 13])
def test_separable_pitch_has_positive_frequency_support_without_claiming_key_count(interval):
    audio, rate, events = paired_wave(48, interval, 0.2, 0, 0.5)
    result = measure_spectral_family(audio, rate, events[1], events)
    assert result["status"] == "upper_frequency_support"
    assert result["upper_supported_partial_count"] >= 2
    assert result["decision"] == "retain"
    assert result["independent_attack_confirmed"] is False


def test_zero_padding_does_not_manufacture_frequency_resolution():
    audio, rate, events = paired_wave(51, 12, 0.2, 0, 0.2)
    coarse = measure_spectral_family(audio, rate, events[1], events, padding_factor=1)
    fine = measure_spectral_family(audio, rate, events[1], events, padding_factor=8)
    assert coarse["effective_bin_width_hz"] == fine["effective_bin_width_hz"]
    assert coarse["window_samples"] == fine["window_samples"]
    assert fine["padded_sample_spacing_hz"] < coarse["padded_sample_spacing_hz"]
    assert coarse["status"] == fine["status"] == "ambiguous"


def test_higher_parent_partials_are_not_assumed_absent_beyond_synth_six_partial_limit():
    audio, rate, events = paired_wave(48, 12, 0.2, 0, 0.5)
    result = measure_spectral_family(audio, rate, events[1], events)
    sixth = next(p for p in result["partials"] if p["order"] == 6)
    assert any(
        p["model_pitch"] == 48 and p["harmonic_order"] == 12
        for p in sixth["compatible_modeled_partials"]
    )
    assert sixth["attribution"] == "overlapping_modeled_family"


def test_other_higher_pitches_are_also_considered_as_competing_explanations():
    audio, rate, events = paired_wave(48, 7, 0.2, 0, 0.5)
    high = NoteEvent(0.2, 0.7, events[1].pitch + 12, 80, 0.8)
    result = measure_spectral_family(audio, rate, events[1], [*events, high])
    assert high.pitch in result["competing_model_pitches"]
    second = next(p for p in result["partials"] if p["order"] == 2)
    assert any(
        p["model_pitch"] == high.pitch and p["harmonic_order"] == 1
        for p in second["compatible_modeled_partials"]
    )


def test_high_order_competing_partials_include_detuning_expansion():
    rate = 22050
    times = np.arange(rate) / rate
    audio = np.sin(2 * np.pi * 440 * 2 ** ((90 - 69) / 12) * times)
    upper = NoteEvent(0.2, 0.7, 90, 80, 0.8)
    lower = NoteEvent(0.2, 0.7, 21, 80, 0.8)
    result = measure_spectral_family(audio, rate, upper, [upper, lower])
    sixth = next(p for p in result["partials"] if p["order"] == 6)
    orders = {
        p["harmonic_order"] for p in sixth["compatible_modeled_partials"] if p["model_pitch"] == 21
    }
    assert set(range(331, 337)) <= orders


@pytest.mark.parametrize("fault", ["old_code", "different_normalization"])
def test_runner_refuses_unverified_inputs_before_writing_output(tmp_path, monkeypatch, fault):
    from scripts import audit_crossing_spectral_family as runner

    previous, baseline, output = tmp_path / "previous", tmp_path / "baseline", tmp_path / "output"
    previous.mkdir()
    baseline.mkdir()
    (baseline / "normalized.wav").write_bytes(b"frozen normalized input")
    (tmp_path / "old_code.py").write_text("changed")
    (previous / "report.json").write_text(
        json.dumps(
            {
                "baseline_hashes": {},
                "audit_code_hashes": {},
                "baseline_pipeline_hashes": {"old_code.py": "outdated"}
                if fault == "old_code"
                else {},
            }
        )
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "INPUT", previous)
    monkeypatch.setattr(runner, "BASELINE", baseline)

    def normalize(source, destination):
        assert fault == "different_normalization"
        destination.write_bytes(b"different normalization")

    monkeypatch.setattr(runner, "preprocess_audio", normalize)
    with pytest.raises(ValueError, match="stale spectral|does not reproduce"):
        runner.run(output)
    assert not output.exists()


@pytest.mark.parametrize("kind", ["short", "silent", "bandwidth"])
def test_insufficient_measurement_keeps_event_and_never_inferrs_absence(kind):
    rate = 22050
    audio = np.zeros(rate)
    event = NoteEvent(0.2, 0.5, 60, 80, 0.8)
    if kind == "short":
        event = NoteEvent(0.2, 0.23, 60, 80, 0.8)
    elif kind == "bandwidth":
        rate = 4000
        event = NoteEvent(0.2, 0.5, 100, 80, 0.8)
    result = measure_spectral_family(audio, rate, event, [event])
    assert result["status"].startswith("insufficient_")
    assert result["decision"] == "retain"
    assert result["independent_attack_confirmed"] is False


def test_invalid_wave_or_rate_is_not_silently_accepted():
    e = NoteEvent(0.2, 0.5, 60, 80, 0.8)
    for audio, rate in (
        (np.zeros(100), 0),
        (np.array([np.nan]), 22050),
        (np.zeros((100, 2)), 22050),
    ):
        with pytest.raises(ValueError):
            measure_spectral_family(audio, rate, e, [e])
    with pytest.raises(ValueError):
        measure_spectral_family(np.zeros(100), 22050, e, [e], padding_factor=0)


def test_frozen_audit_inputs_and_code_match_report():
    report = json.loads((OUTPUT / "report.json").read_text())
    for group in ("input_hashes", "code_hashes"):
        assert all(file_sha256(ROOT / p) == digest for p, digest in report[group].items())
    assert report["candidate_count"] == len(report["candidates"]) == 22
    assert report["probe_count"] == len(report["probes"]) == 120
    assert report["candidate_status_counts"] == {"ambiguous": 22}
    assert report["probe_status_counts"] == {
        "natural_partial_only": {"ambiguous": 12},
        "real_simultaneous_note": {"ambiguous": 108},
    }
    assert report["new_deletion_count"] == 0
    assert report["production_eligible"] is False


def test_saved_control_measurements_reproduce_from_wavs():
    previous = json.loads((PREVIOUS / "report.json").read_text())
    report = json.loads((OUTPUT / "report.json").read_text())
    by_id = {p["id"]: p for p in report["probes"]}
    for probe in previous["probes"]:
        audio, rate = sf.read(PREVIOUS / probe["wav"])
        events = [NoteEvent(**e) for e in probe["candidate_events"]]
        result = measure_spectral_family(audio, rate, events[1], events)
        assert by_id[probe["id"]]["measurement"] == result
        assert result["decision"] == "retain"
