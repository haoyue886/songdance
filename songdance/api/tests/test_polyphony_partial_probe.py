import json
from dataclasses import replace

import pytest

from scripts.polyphony_partial_probe import measure
from scripts.run_polyphony_partial_probe import control, run


@pytest.mark.parametrize("pitch", [55, 60, 64])
def test_clean_decay_and_weak_restrike(pitch):
    for level in (0, 0.01, 0.04):
        audio, rate, events = control(pitch, level, 1.57, 0)
        result = measure(audio, rate, events[1], events)
        if level:
            assert not result["continuous_hypothesis"]
        assert any(t["status"] == "frequency_collision" for t in result["tracks"])


def test_boundary_and_no_signal_abstain():
    audio, rate, events = control(60, 0, 0, 0)
    assert measure(audio, rate, replace(events[1], start_sec=0.01), events)["status"] == "boundary"
    assert not measure(audio * 0, rate, events[1], events)["continuous_hypothesis"]


def test_real_run_and_immutable_output(tmp_path):
    out = tmp_path / "probe"
    report = run(out)
    assert len(report["controls"]) == 36
    assert len(report["events"]) == 149
    for truth, expected in (("decay", True), ("restrike", False)):
        rows = [c for c in report["controls"] if c["truth"] == truth]
        assert len(rows) == (12 if truth == "decay" else 24)
        assert all(c["measurement"]["continuous_hypothesis"] is expected for c in rows)
    assert report["selected_indices"] == []
    assert report["control_restrike_false_selections"] == 0
    assert report["actual_applied_deletions"] == 0
    assert report["production_eligible"] is False
    assert report["metrics_onsets_only"]["matched_count"] == 120
    assert not list(out.glob("*.mid"))
    before = (out / "audit.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(out)
    assert (out / "audit.json").read_bytes() == before


def test_failed_measurement_is_recorded(tmp_path, monkeypatch):
    from scripts import run_polyphony_partial_probe as runner

    def fail(*args):
        raise ValueError("probe failed")

    monkeypatch.setattr(runner, "measure", fail)
    out = tmp_path / "failure"
    with pytest.raises(ValueError, match="probe failed"):
        runner.run(out)
    assert json.loads((out / "status.json").read_text())["status"] == "failed"
    assert not (out / "audit.json").exists()


def test_nondecaying_or_invalid_track_vetoes_continuity():
    from scripts.polyphony_partial_probe import supports_continuity

    tracks = [{"status": "measured", "error": 0.001}] * 2
    assert supports_continuity(tracks)
    assert not supports_continuity(tracks + [{"status": "nondecaying"}])
    for value in (float("nan"), float("inf"), -0.01, 0.011):
        assert not supports_continuity(tracks + [{"status": "measured", "error": value}])


def test_growing_partial_in_audio_vetoes_other_decaying_partials():
    import numpy as np

    from app.pipeline.transcribe import NoteEvent

    rate = 22050
    time = np.arange(2 * rate) / rate
    frequency = 440 * 2 ** ((60 - 69) / 12)
    audio = sum(
        0.1
        / h
        * np.exp((2.6 if h == 3 else -2.6) * (time - 0.8))
        * np.sin(2 * np.pi * frequency * h * time)
        for h in range(1, 5)
    )
    event = NoteEvent(0.8, 1.2, 60, 80, 0)
    result = measure(audio, rate, event, [event])
    assert any(t["status"] == "nondecaying" for t in result["tracks"])
    assert not result["continuous_hypothesis"]
