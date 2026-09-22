import numpy as np
import pytest

from scripts.sustain_reattack_candidate import rebuild


def note(pitch, start, end):
    return {"pitch": pitch, "start_sec": start, "end_sec": end, "velocity": 80}


def signal(kind):
    rate = 22050
    t = np.arange(2 * rate) / rate
    f = 440 * 2 ** ((60 - 69) / 12)
    decay = 0.04 * np.exp(-3 * t) * np.sin(2 * np.pi * f * t)
    onset = np.maximum(t - 1, 0)
    attack = (t >= 1) * np.minimum(onset / 0.008, 1) * np.exp(-3 * onset)
    if kind == "reattack":
        return decay + 0.08 * attack * np.sin(2 * np.pi * f * onset)
    if kind == "other":
        return decay + 0.4 * attack * np.sin(2 * np.pi * 329.63 * onset)
    if kind == "noise":
        return decay + 0.001 * np.random.default_rng(42).normal(size=len(t))
    if kind == "lower_octave":
        return decay + attack * (
            0.2 * np.sin(np.pi * f * onset) + 0.08 * np.sin(2 * np.pi * f * onset)
        )
    return decay


@pytest.mark.parametrize("kind", ("decay", "noise", "other", "lower_octave"))
def test_no_false_split_on_control(kind):
    parent = [note(60, 0, 2)]
    secondary = [note(60, 1, 1.5)]
    if kind == "lower_octave":
        secondary.append(note(48, 1, 1.5))
    output, audit = rebuild(signal(kind), 22050, parent, secondary)
    assert output == parent
    assert audit[0]["decision"] == "retain"


def test_supported_reattack_splits_but_preserves_pitch_and_total_span():
    parent = [note(60, 0, 2)]
    output, audit = rebuild(signal("reattack"), 22050, parent, [note(60, 1, 1.5)])
    assert [(n["start_sec"], n["end_sec"]) for n in output] == [(0, 1), (1, 2)]
    assert [n["pitch"] for n in output] == [60, 60]
    assert parent == [note(60, 0, 2)]
    assert audit[0]["decision"] == "experimental_split"


def test_missing_second_model_onset_never_creates_a_note():
    parent = [note(60, 0, 2)]
    output, audit = rebuild(signal("reattack"), 22050, parent, [])
    assert output == parent and audit == []


def test_actual_candidate_recomputes_without_reference_driven_selection():
    import json

    import soundfile as sf

    from scripts.compare_piano_model_outputs import note_metrics, read_midi
    from scripts.piano_comparison_cases import ROOT, file_sha256

    root = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1"
    source = json.loads((root / "comparison.json").read_text())
    report = json.loads((root / "reattack-v1/audit.json").read_text())
    audio, rate = sf.read(root / "normalized.wav")
    events, proposals = rebuild(
        audio, rate, source["models"]["transkun"]["events"], source["models"]["basic"]["events"]
    )
    assert report["events"] == events and report["proposals"] == proposals
    assert report["comparison_sha256"] == file_sha256(root / "comparison.json")
    assert report["candidate_midi_sha256"] == file_sha256(root / "reattack-v1/candidate.mid")
    reference = read_midi(
        ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-source-v1/reference.mid"
    )
    assert report["metrics"] == {str(t): note_metrics(reference, events, t) for t in (0.05, 0.1)}
    assert report["metrics"]["0.05"]["matched_count"] == 43
    assert report["metrics"]["0.05"]["extra_count"] == 0
    assert len(events) == 43
    assert report["production_eligible"] is False
