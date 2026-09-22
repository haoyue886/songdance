import numpy as np

from scripts.audit_device_bass_audio import evidence
from scripts.evaluate_device_context_shift import restore


def note(start, end):
    return {"pitch": 36, "velocity": 70, "start_sec": start, "end_sec": end}


def test_restoration_keeps_relative_time_and_explicitly_audits_boundaries():
    notes = [note(3.9, 4.2), note(4, 4.8), note(19, 19.8), note(33.8, 34.2), note(34, 35)]
    kept, clipped, rejected = restore(notes, 4, 30)
    assert [(n["start_sec"], n["end_sec"]) for n in kept] == [
        (0, 0.7999999999999998),
        (15, 15.8),
        (29.799999999999997, 30),
    ]
    assert len(clipped) == 1
    assert rejected == [notes[0], notes[-1]]
    assert notes[3]["end_sec"] == 34.2


def test_decaying_residual_without_restrike_cannot_confirm_attack():
    rate = 22050
    time = np.arange(rate * 2) / rate
    audio = 0.05 * np.exp(-3 * time) * np.sin(2 * np.pi * 65.4064 * time)
    result = evidence(audio, rate, {"pitch": 36, "start_sec": 1})
    assert result["after_amplitude"] < result["before_amplitude"]
    assert result["independent_attack_confirmed"] is False


def test_small_negative_onset_is_restored_with_explicit_audit():
    source = note(3.996, 4.4)
    kept, adjusted, rejected = restore([source], 4, 30)
    assert kept[0]["start_sec"] == 0
    assert adjusted == [{"before": source, "after": kept[0]}]
    assert rejected == []
    assert source["start_sec"] == 3.996


def test_padding_only_note_and_early_attack_are_not_invented_at_zero():
    notes = [note(3.995, 3.999), note(3.98, 4.5)]
    kept, adjusted, rejected = restore(notes, 4, 30)
    assert kept == adjusted == []
    assert rejected == notes
