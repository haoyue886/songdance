import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import librosa
import numpy as np

from app.pipeline.analysis_features import (
    DEFAULT_KEY_SIGNATURE,
)
from app.pipeline.analysis_features import (
    rank_key_candidates as _rank_key_candidates,
)
from app.pipeline.analysis_features import (
    rank_meter_candidates as _rank_meter_candidates,
)
from app.pipeline.errors import StructureAnalysisError

ANALYSIS_ALGORITHM_VERSION = "structure-analysis-v2"
DEFAULT_BPM = 120.0
DEFAULT_TIME_SIGNATURE = "4/4"
TEMPO_DEFAULTED = "TEMPO_DEFAULTED"
TIME_SIGNATURE_DEFAULTED = "TIME_SIGNATURE_DEFAULTED_4_4"
KEY_SIGNATURE_DEFAULTED = "KEY_SIGNATURE_DEFAULTED_C_MAJOR"
ANALYSIS_DISABLED = "STRUCTURE_ANALYSIS_DISABLED"

@dataclass(frozen=True)
class AnalysisConfig:
    enabled: bool = True
    sample_rate: int = 22_050
    hop_length: int = 512
    min_tempo_confidence: float = 0.2
    min_meter_confidence: float = 0.6
    min_key_confidence: float = 0.18
    timeout_seconds: float = 15.0
    max_duration_seconds: float = 90.0

    def as_dict(self) -> dict[str, bool | float | int]:
        return asdict(self)

    @property
    def version(self) -> str:
        payload = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{ANALYSIS_ALGORITHM_VERSION}/{fingerprint}"


@dataclass(frozen=True)
class StructureAnalysis:
    status: str
    version: str
    source: str
    bpm: float
    bpm_confidence: float
    beat_grid_seconds: tuple[float, ...]
    downbeat_grid_seconds: tuple[float, ...]
    downbeat_phase_index: int
    time_signature: str
    time_signature_confidence: float
    time_signature_source: str
    time_signature_candidates: tuple[dict[str, float | str], ...]
    key_signature: str
    key_confidence: float
    key_signature_source: str
    key_candidates: tuple[dict[str, float | str], ...]
    duration_seconds: float
    elapsed_seconds: float
    reason_codes: tuple[str, ...]

    def summary(self) -> dict[str, object]:
        return asdict(self)


def analyze_audio(
    source: Path, config: AnalysisConfig | None = None
) -> StructureAnalysis:
    active = config or AnalysisConfig()
    _validate_config(active)
    if not active.enabled:
        return fallback_analysis(active, ANALYSIS_DISABLED, source="disabled")

    from app.pipeline.analysis_runtime import run_with_timeout

    started = time.perf_counter()
    result = run_with_timeout(
        _analyze_audio_core, (source, active), active.timeout_seconds
    )
    return replace(result, elapsed_seconds=round(time.perf_counter() - started, 6))


def _analyze_audio_core(source: Path, active: AnalysisConfig) -> StructureAnalysis:

    started = time.perf_counter()
    try:
        audio, sample_rate = librosa.load(
            source, sr=active.sample_rate, mono=True, duration=active.max_duration_seconds
        )
        if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-8:
            raise StructureAnalysisError("音频结构分析没有收到有效信号")
        _raise_if_timed_out(started, active)
        onset_envelope = librosa.onset.onset_strength(
            y=audio, sr=sample_rate, hop_length=active.hop_length
        )
        bass_onset_envelope = librosa.onset.onset_strength(
            y=audio,
            sr=sample_rate,
            hop_length=active.hop_length,
            feature=librosa.feature.melspectrogram,
            fmax=300,
            n_mels=32,
        )
        tempo, beat_frames = librosa.beat.beat_track(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=active.hop_length,
            sparse=True,
        )
        _raise_if_timed_out(started, active)
        beat_frames = np.asarray(beat_frames, dtype=int)
        bpm = _scalar_tempo(tempo)
        tempo_confidence = _tempo_confidence(onset_envelope, beat_frames)
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=active.hop_length
        )
        meter_candidates = _rank_meter_candidates(
            onset_envelope, beat_frames, bass_onset_envelope
        )
        key_candidates = _rank_key_candidates(
            librosa.feature.chroma_cqt(
                y=audio, sr=sample_rate, hop_length=active.hop_length
            )
        )
        _raise_if_timed_out(started, active)
    except StructureAnalysisError:
        raise
    except Exception as error:
        raise StructureAnalysisError() from error

    reasons: list[str] = []
    if not math.isfinite(bpm) or bpm <= 0 or tempo_confidence < active.min_tempo_confidence:
        bpm = DEFAULT_BPM
        tempo_confidence = 0.0
        beat_times = np.asarray([], dtype=float)
        reasons.append(TEMPO_DEFAULTED)
    selected_meter = meter_candidates[0]
    meter_confidence = float(selected_meter["confidence"])
    if meter_confidence < active.min_meter_confidence:
        time_signature = DEFAULT_TIME_SIGNATURE
        downbeat_phase = 0
        meter_source = "default"
        reasons.append(TIME_SIGNATURE_DEFAULTED)
    else:
        time_signature = str(selected_meter["value"])
        downbeat_phase = int(selected_meter["phase"])
        meter_source = "librosa_onset_accent"
    selected_key = key_candidates[0]
    key_confidence = float(selected_key["confidence"])
    if key_confidence < active.min_key_confidence:
        key_signature = DEFAULT_KEY_SIGNATURE
        key_source = "default"
        reasons.append(KEY_SIGNATURE_DEFAULTED)
    else:
        key_signature = str(selected_key["value"])
        key_source = "librosa_chroma_krumhansl"
    downbeats = _downbeats(beat_times, time_signature, downbeat_phase)
    elapsed = time.perf_counter() - started
    return StructureAnalysis(
        status="analyzed" if not reasons else "analyzed_with_defaults",
        version=active.version,
        source="librosa-0.11.0",
        bpm=round(float(bpm), 6),
        bpm_confidence=round(tempo_confidence, 6),
        beat_grid_seconds=tuple(round(float(value), 6) for value in beat_times),
        downbeat_grid_seconds=tuple(round(value, 6) for value in downbeats),
        downbeat_phase_index=downbeat_phase,
        time_signature=time_signature,
        time_signature_confidence=round(meter_confidence, 6),
        time_signature_source=meter_source,
        time_signature_candidates=tuple(meter_candidates),
        key_signature=key_signature,
        key_confidence=round(key_confidence, 6),
        key_signature_source=key_source,
        key_candidates=tuple(key_candidates),
        duration_seconds=round(len(audio) / sample_rate, 6),
        elapsed_seconds=round(elapsed, 6),
        reason_codes=tuple(reasons),
    )


def fallback_analysis(
    config: AnalysisConfig,
    reason_code: str,
    *,
    source: str = "fallback",
) -> StructureAnalysis:
    return StructureAnalysis(
        status="disabled" if reason_code == ANALYSIS_DISABLED else "failed",
        version=config.version,
        source=source,
        bpm=DEFAULT_BPM,
        bpm_confidence=0.0,
        beat_grid_seconds=(),
        downbeat_grid_seconds=(),
        downbeat_phase_index=0,
        time_signature=DEFAULT_TIME_SIGNATURE,
        time_signature_confidence=0.0,
        time_signature_source="default",
        time_signature_candidates=(),
        key_signature=DEFAULT_KEY_SIGNATURE,
        key_confidence=0.0,
        key_signature_source="default",
        key_candidates=(),
        duration_seconds=0.0,
        elapsed_seconds=0.0,
        reason_codes=(
            reason_code,
            TEMPO_DEFAULTED,
            TIME_SIGNATURE_DEFAULTED,
            KEY_SIGNATURE_DEFAULTED,
        ),
    )


def _tempo_confidence(onset_envelope: np.ndarray, beat_frames: np.ndarray) -> float:
    if beat_frames.size < 2 or onset_envelope.size == 0:
        return 0.0
    strengths = onset_envelope[np.clip(beat_frames, 0, len(onset_envelope) - 1)]
    scale = float(np.percentile(onset_envelope, 95)) + 1e-9
    return float(np.clip(np.mean(strengths) / scale, 0.0, 1.0))


def _scalar_tempo(tempo: np.ndarray | float) -> float:
    values = np.asarray(tempo, dtype=float).reshape(-1)
    return float(values[0]) if values.size else 0.0


def _downbeats(
    beat_times: np.ndarray, time_signature: str, phase: int
) -> tuple[float, ...]:
    group_size = {"3/4": 3, "4/4": 4, "6/8": 3}[time_signature]
    selected = [float(value) for value in beat_times[phase::group_size]]
    if len(selected) >= 2:
        measure_interval = float(np.median(np.diff(selected)))
        previous = selected[0] - measure_interval
        if previous >= 0:
            selected.insert(0, previous)
    return tuple(selected)


def _raise_if_timed_out(started: float, config: AnalysisConfig) -> None:
    if time.perf_counter() - started > config.timeout_seconds:
        raise StructureAnalysisError("音频结构分析超时", code="STRUCTURE_ANALYSIS_TIMEOUT")


def _validate_config(config: AnalysisConfig) -> None:
    if config.sample_rate < 8_000 or config.sample_rate > 48_000:
        raise ValueError("analysis sample rate must be between 8000 and 48000")
    if config.hop_length < 128 or config.hop_length > 4096:
        raise ValueError("analysis hop length must be between 128 and 4096")
    confidences = (
        config.min_tempo_confidence,
        config.min_meter_confidence,
        config.min_key_confidence,
    )
    if any(not 0 <= value <= 1 for value in confidences):
        raise ValueError("analysis confidence thresholds must be between 0 and 1")
    if not 0 < config.timeout_seconds <= 15:
        raise ValueError("analysis timeout must be greater than 0 and at most 15 seconds")
    if not 1 <= config.max_duration_seconds <= 90:
        raise ValueError("analysis duration must be between 1 and 90 seconds")
