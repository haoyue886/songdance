import numpy as np
import pytest

from scripts.sustain_missing_note_candidate import propose


def note(pitch, start=1, end=1.5):
    return {"pitch": pitch, "start_sec": start, "end_sec": end, "velocity": 80}


def wave(pitch):
    rate = 22050
    time = np.arange(2 * rate) / rate
    elapsed = np.maximum(time - 1, 0)
    frequency = 440 * 2 ** ((pitch - 69) / 12)
    return (
        0.1
        * (time >= 1)
        * np.minimum(elapsed / 0.008, 1)
        * np.exp(-2 * elapsed)
        * np.sin(2 * np.pi * frequency * elapsed)
    )


def test_independent_low_note_can_be_proposed_without_reference():
    retained = [note(64)]
    output, audit = propose(wave(55) + wave(64), 22050, retained, [note(55), note(64)])
    assert sorted(n["pitch"] for n in output) == [55, 64]
    assert audit[0]["decision"] == "experimental_add"
    assert retained == [note(64)]


@pytest.mark.parametrize("control", ("silence", "other_pitch", "noise", "octave_harmonic"))
def test_negative_controls_cannot_create_missing_pitch(control):
    retained = [note(64)]
    if control == "silence":
        audio = np.zeros(44100)
    elif control == "other_pitch":
        audio = wave(64)
    elif control == "noise":
        audio = 0.001 * np.random.default_rng(42).normal(size=44100)
    else:
        audio = wave(43) + wave(55)
        retained.append(note(43))
    output, audit = propose(audio, 22050, retained, [note(55)])
    assert len(output) == len(retained)
    assert audit[0]["decision"] == "abstain"


def test_no_pre_attack_window_abstains_instead_of_guessing_first_note():
    output, audit = propose(wave(55), 22050, [note(64)], [note(55, 0.05, 0.5)])
    assert len(output) == 1
    assert audit[0]["decision"] == "abstain"


def test_actual_output_recomputes_and_preserves_retained_notes():
    import json

    import soundfile as sf

    from scripts.compare_piano_model_outputs import note_metrics, read_midi
    from scripts.piano_comparison_cases import ROOT, file_sha256

    root = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1"
    source = json.loads((root / "comparison.json").read_text())
    prior = json.loads((root / "reattack-v1/audit.json").read_text())
    report = json.loads((root / "missing-notes-v2/audit.json").read_text())
    audio, rate = sf.read(root / "normalized.wav")
    events, audit = propose(audio, rate, prior["events"], source["models"]["basic"]["events"])
    assert events == report["events"] and audit == report["audit"]
    assert all(n in events for n in prior["events"])
    assert len(events) == 45
    assert len(audit) == 35
    assert sum(row["decision"] == "experimental_add" for row in audit) == 2
    midi = root / "missing-notes-v2/candidate.mid"
    assert file_sha256(midi) == report["midi_sha256"]
    reference = read_midi(
        ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-source-v1/reference.mid"
    )
    assert report["metrics"] == {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)}
    parsed = note_metrics(reference, read_midi(midi), 0.05)
    assert (
        parsed["matched_count"] == 45
        and parsed["extra_count"] == 0
        and parsed["missing_count"] == 0
    )
    assert report["production_eligible"] is False
