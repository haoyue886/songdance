import json
import time
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile as sf

from app.pipeline.analysis import (
    ANALYSIS_DISABLED,
    AnalysisConfig,
    StructureAnalysis,
    _analyze_audio_core,
    _downbeats,
    _rank_key_candidates,
    _rank_meter_candidates,
    analyze_audio,
    fallback_analysis,
)
from app.pipeline.errors import StructureAnalysisError
from app.pipeline.quantize import quantize_events
from app.pipeline.transcribe import NoteEvent
from app.services.transcription import run_transcription_job
from app.services.transcription_analysis import analyze_with_fallback
from tests.test_jobs import create_job
from tests.test_transcription_service import fake_transcription


def test_analysis_config_version_is_stable_and_changes_with_config() -> None:
    assert AnalysisConfig().version == AnalysisConfig().version
    assert AnalysisConfig().version != AnalysisConfig(hop_length=256).version


def test_disabled_analysis_returns_explicit_defaults() -> None:
    result = fallback_analysis(AnalysisConfig(enabled=False), ANALYSIS_DISABLED, source="disabled")

    assert result.status == "disabled"
    assert result.bpm == 120
    assert result.time_signature == "4/4"
    assert result.key_signature == "C major"
    assert result.beat_grid_seconds == ()
    assert ANALYSIS_DISABLED in result.reason_codes


def test_analysis_rejects_silent_audio(tmp_path: Path) -> None:
    source = tmp_path / "silent.wav"
    sf.write(source, np.zeros(22_050, dtype=np.float32), 22_050)

    with pytest.raises(StructureAnalysisError, match="有效信号"):
        analyze_audio(source)


def test_analysis_timeout_terminates_execution(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    times = np.arange(22_050, dtype=np.float32) / 22_050
    sf.write(source, np.sin(2 * np.pi * 440 * times), 22_050)
    started = time.monotonic()

    with pytest.raises(StructureAnalysisError) as captured:
        analyze_audio(source, AnalysisConfig(timeout_seconds=0.05))

    assert captured.value.code == "STRUCTURE_ANALYSIS_TIMEOUT"
    assert time.monotonic() - started < 1.0


def test_analysis_domain_error_becomes_explicit_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.transcription_analysis.analyze_audio",
        lambda *_args: (_ for _ in ()).throw(
            StructureAnalysisError(code="STRUCTURE_ANALYSIS_TIMEOUT")
        ),
    )

    result = analyze_with_fallback(Path("unused.wav"), AnalysisConfig(), "fixture-job")

    assert result.status == "failed"
    assert "STRUCTURE_ANALYSIS_TIMEOUT" in result.reason_codes


@pytest.mark.parametrize(
    "meter,strong_every,midpoint_strength",
    [("3/4", 3, 0.0), ("4/4", 4, 0.0), ("6/8", 3, 1.5)],
)
def test_meter_candidates_distinguish_supported_meters(
    meter: str, strong_every: int, midpoint_strength: float
) -> None:
    beat_frames = np.arange(10, 250, 10)
    envelope = np.zeros(260)
    envelope[beat_frames] = 0.2
    envelope[beat_frames[::strong_every]] = 2.0
    midpoints = ((beat_frames[:-1] + beat_frames[1:]) / 2).astype(int)
    envelope[midpoints] = midpoint_strength

    candidates = _rank_meter_candidates(envelope, beat_frames)

    assert candidates[0]["value"] == meter
    assert float(candidates[0]["confidence"]) > 0.35


def test_meter_candidates_preserve_winning_downbeat_phase() -> None:
    beat_frames = np.arange(10, 130, 10)
    envelope = np.zeros(140)
    envelope[beat_frames] = 0.2
    envelope[beat_frames[1::3]] = 2.0

    winner = _rank_meter_candidates(envelope, beat_frames)[0]
    beat_times = beat_frames / 10

    assert winner["value"] == "3/4"
    assert winner["phase"] == 1
    assert _downbeats(beat_times, "3/4", int(winner["phase"])) == (2.0, 5.0, 8.0, 11.0)


def test_key_candidates_detect_c_major_profile() -> None:
    chroma = np.zeros((12, 8))
    chroma[[0, 4, 7]] = np.asarray([[1.0], [0.8], [0.9]])

    candidates = _rank_key_candidates(chroma)

    assert candidates[0]["value"] == "C major"
    assert float(candidates[0]["confidence"]) > 0


def test_quantize_uses_analysis_grid_without_mutating_raw_events() -> None:
    raw = [NoteEvent(0.12, 0.37, 60, 90, 0.9)]
    analysis = StructureAnalysis(
        status="analyzed",
        version="fixture",
        source="fixture",
        bpm=120,
        bpm_confidence=1,
        beat_grid_seconds=(0.1, 0.6, 1.1),
        downbeat_grid_seconds=(0.1,),
        downbeat_phase_index=0,
        time_signature="3/4",
        time_signature_confidence=1,
        time_signature_source="fixture",
        time_signature_candidates=(),
        key_signature="G major",
        key_confidence=1,
        key_signature_source="fixture",
        key_candidates=(),
        duration_seconds=1,
        elapsed_seconds=0,
        reason_codes=(),
    )

    quantized = quantize_events(raw, analysis)

    assert raw[0].start_sec == 0.12
    assert quantized == [NoteEvent(0.1, 0.35, 60, 90, 0.9)]


def test_analysis_config_allows_the_product_audio_window() -> None:
    assert AnalysisConfig().max_duration_seconds == 90.0
    assert AnalysisConfig(max_duration_seconds=60).version != AnalysisConfig().version


def test_analysis_loads_the_configured_audio_window(monkeypatch) -> None:
    load = Mock(return_value=(np.zeros(1, dtype=np.float32), 22_050))
    monkeypatch.setattr("app.pipeline.analysis.librosa.load", load)

    with pytest.raises(StructureAnalysisError, match="有效信号"):
        _analyze_audio_core(Path("fixture.wav"), AnalysisConfig())

    load.assert_called_once_with(Path("fixture.wav"), sr=22_050, mono=True, duration=90.0)


def test_service_persists_analysis_without_changing_raw_timeline(
    api_client, monkeypatch
) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription_analysis.analyze_audio",
        lambda *_args, **_kwargs: _fixture_analysis(),
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    root = storage_path / f"jobs/{job_id}/artifacts/attempt-1"
    raw = json.loads((root / "raw-timeline.json").read_text())
    cleaned = json.loads((root / "timeline.json").read_text())
    report = json.loads(client.get(f"/jobs/{job_id}").json()["quality_report"]["summary"])
    assert raw["time_signature"] == "4/4"
    assert "analysis" not in raw
    assert cleaned["time_signature"] == "3/4"
    assert cleaned["key_signature"] == "G major"
    assert cleaned["beat_grid_seconds"] == [0.0, 0.5, 1.0, 1.5]
    assert report["analysis"]["source"] == "fixture"


def test_service_falls_back_when_structure_analysis_crashes(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    monkeypatch.setattr(
        "app.services.transcription_analysis.analyze_audio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("analysis bug")),
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    payload = client.get(f"/jobs/{job_id}").json()
    timeline = json.loads(
        (
            storage_path / f"jobs/{job_id}/artifacts/attempt-1/timeline.json"
        ).read_text()
    )
    report = json.loads(payload["quality_report"]["summary"])
    assert payload["status"] == "succeeded"
    assert timeline["time_signature"] == "4/4"
    assert timeline["key_signature"] == "C major"
    assert "STRUCTURE_ANALYSIS_UNEXPECTED_ERROR" in report["analysis"]["reason_codes"]


def _fixture_analysis() -> StructureAnalysis:
    return StructureAnalysis(
        status="analyzed",
        version="structure-analysis-v1/fixture",
        source="fixture",
        bpm=120,
        bpm_confidence=1,
        beat_grid_seconds=(0.0, 0.5, 1.0, 1.5),
        downbeat_grid_seconds=(0.0, 1.5),
        downbeat_phase_index=0,
        time_signature="3/4",
        time_signature_confidence=0.9,
        time_signature_source="fixture",
        time_signature_candidates=({"value": "3/4", "confidence": 0.9},),
        key_signature="G major",
        key_confidence=0.8,
        key_signature_source="fixture",
        key_candidates=({"value": "G major", "confidence": 0.8},),
        duration_seconds=2,
        elapsed_seconds=0.01,
        reason_codes=(),
    )
