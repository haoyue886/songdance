import numpy as np
import pytest

from app.pipeline.stable_beat_grid import calibrate


def test_frame_quantization_recovers_consistent_tempo_and_grid():
    frame = 512 / 22050
    true = 0.04 + np.arange(60) * 0.5
    beats = np.round(true / frame) * frame
    bpm, grid, audit = calibrate(117.453835, beats, frame)
    assert audit["status"] == "calibrated"
    assert abs(bpm - 120) < 0.05
    assert np.max(np.abs(grid - true)) < 0.005
    assert np.max(np.abs(np.diff(grid) - 60 / bpm)) < 1e-10
    assert audit["original_beats"] == beats.tolist()


@pytest.mark.parametrize("kind", ["accelerando", "missing", "rubato", "tempo_mismatch"])
def test_variable_or_unreliable_beats_are_unchanged(kind):
    beats = 0.04 + np.arange(60) * 0.5
    if kind == "accelerando":
        beats += 0.0004 * np.arange(60) ** 2
    elif kind == "missing":
        beats = np.delete(beats, 20)
    elif kind == "rubato":
        beats += 0.08 * np.sin(np.arange(60) / 4)
    bpm = 80 if kind == "tempo_mismatch" else 120
    output, grid, audit = calibrate(bpm, beats, 512 / 22050)
    assert audit["status"] == "retained"
    assert output == bpm
    assert np.array_equal(grid, beats)


def test_short_track_is_not_extrapolated():
    bpm, grid, audit = calibrate(117, [1, 1.5, 2], 512 / 22050)
    assert audit["status"] == "retained" and bpm == 117


def test_recorded_real_performance_grids_are_not_forced_to_constant_tempo():
    import json
    from pathlib import Path

    root = (
        Path(__file__).parent
        / "fixtures/audio/candidates/closeout-review-20260919-v1/human-review-artifacts"
    )
    paths = list(root.glob("*/timeline.json"))
    assert len(paths) == 10
    for path in paths:
        analysis = json.loads(path.read_text())["analysis"]
        bpm, grid, audit = calibrate(analysis["bpm"], analysis["beat_grid_seconds"], 512 / 22050)
        assert audit["status"] == "retained", path.parent.name
        assert bpm == analysis["bpm"]
        assert grid.tolist() == analysis["beat_grid_seconds"]


def test_actual_device_rebuild_recovers_timing_without_changing_raw_midi():
    import json
    from pathlib import Path

    from scripts.compare_piano_model_outputs import note_metrics, read_midi

    root = Path(__file__).parent / "fixtures/audio"
    new = root / "candidates/10-stable-grid-v2"
    old = root / "candidates/closeout-review-20260919-v1/structure-review-artifacts/10-device"
    assert read_midi(new / "raw.mid") == read_midi(old / "raw.mid")
    report = json.loads((new / "validation.json").read_text())
    assert report["analysis"]["tempo_grid_evidence"]["status"] == "calibrated"
    ref = [n for n in read_midi(root / "generated/10-device.mid") if n["pitch"] < 60]
    notes = [n for n in read_midi(new / "score.mid") if n["pitch"] < 60]
    for tolerance in (0.05, 0.1):
        metrics = note_metrics(ref, notes, tolerance)
        assert report["bass_metrics"][str(tolerance)] == metrics
        assert metrics["matched_count"] == 29
    assert report["production_eligible"] is False


def test_subframe_tempo_variation_is_within_tolerance_not_proven_constant():
    frame = 512 / 22050
    times = 0.1 + np.r_[0, np.cumsum(np.linspace(0.495, 0.505, 13))]
    observed = np.round(times / frame) * frame
    _, grid, audit = calibrate(120, observed, frame)
    assert audit["status"] == "calibrated"
    assert np.max(np.abs(grid - observed)) <= frame
    # A passing fit cannot distinguish small rubato from frame quantization.
    assert audit["original_beats"] == observed.tolist()


def test_current_audio_analysis_to_notation_recovers_device_timing(tmp_path):
    from pathlib import Path

    import pretty_midi

    from app.pipeline.analysis import analyze_audio
    from app.pipeline.cleanup import clean_note_events
    from app.pipeline.harmonics import extract_harmonic_evidence
    from app.pipeline.score import build_score, write_quantized_midi
    from app.pipeline.sustain import extract_sustain_evidence
    from app.pipeline.transcribe import transcribe_audio
    from scripts.compare_piano_model_outputs import note_metrics, read_midi

    root = Path(__file__).parent / "fixtures/audio"
    normalized = root / "candidates/10-stable-grid-v2/normalized.wav"
    analysis = analyze_audio(normalized)
    assert analysis.tempo_grid_evidence["status"] == "calibrated"
    assert analysis.tempo_grid_evidence["original_bpm"] == pytest.approx(117.453835, abs=1e-5)
    assert analysis.bpm == pytest.approx(120, abs=0.05)
    events, raw = transcribe_audio(normalized)
    evidence = extract_harmonic_evidence(normalized, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)
    scored = build_score(
        cleaned.events,
        analysis=analysis,
        harmonic_evidence=evidence,
        sustain_evidence=extract_sustain_evidence(normalized, raw),
    )
    output = tmp_path / "current.mid"
    write_quantized_midi(scored, output)
    assert pretty_midi.PrettyMIDI(str(output)).instruments
    reference = [n for n in read_midi(root / "generated/10-device.mid") if n["pitch"] < 60]
    estimated = [n for n in read_midi(output) if n["pitch"] < 60]
    for tolerance in (0.05, 0.1):
        metrics = note_metrics(reference, estimated, tolerance)
        assert metrics["matched_count"] == 29
        assert metrics["extra_count"] == 49
