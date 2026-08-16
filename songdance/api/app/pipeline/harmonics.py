import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import librosa
import numpy as np

from app.pipeline.transcribe import NoteEvent

HARMONIC_EVIDENCE_VERSION = "harmonic-evidence-v1"
HARMONIC_AUDIO_EVIDENCE = "HARMONIC_AUDIO_EVIDENCE"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarmonicEvidenceConfig:
    sample_rate: int = 22_050
    hop_length: int = 256
    n_fft: int = 4096
    maximum_harmonic_order: int = 6
    tuning_tolerance_cents: float = 35.0
    maximum_energy_ratio: float = 0.22
    onset_alignment_tolerance_seconds: float = 0.08
    onset_window_seconds: float = 0.08
    minimum_independent_onset_growth: float = 2.0

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{HARMONIC_EVIDENCE_VERSION}/{digest}"


@dataclass(frozen=True)
class HarmonicRemoval:
    fundamental_pitch: int
    harmonic_pitch: int
    harmonic_start_sec: float
    harmonic_end_sec: float
    harmonic_number: int
    tuning_error_cents: float
    energy_ratio: float
    independent_onset: bool
    reason: str = HARMONIC_AUDIO_EVIDENCE

    def summary(self) -> dict[str, object]:
        return asdict(self)

    def matches(self, event: NoteEvent) -> bool:
        return (
            event.pitch == self.harmonic_pitch
            and event.start_sec == self.harmonic_start_sec
            and event.end_sec == self.harmonic_end_sec
        )


@dataclass(frozen=True)
class HarmonicEvidence:
    version: str
    status: str
    source: str | None
    removals: tuple[HarmonicRemoval, ...]

    @classmethod
    def unavailable(cls) -> "HarmonicEvidence":
        return cls(
            version=HarmonicEvidenceConfig().version,
            status="unavailable",
            source=None,
            removals=(),
        )

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "removed_candidate_count": len(self.removals),
            "removals": [item.summary() for item in self.removals],
        }


def extract_harmonic_evidence(
    audio_path: Path,
    events: list[NoteEvent],
    config: HarmonicEvidenceConfig | None = None,
) -> HarmonicEvidence:
    active = config or HarmonicEvidenceConfig()
    try:
        audio, sample_rate = _load_audio(audio_path, active)
        spectrum = np.abs(
            librosa.stft(
                audio,
                n_fft=active.n_fft,
                hop_length=active.hop_length,
                window="hann",
            )
        ) ** 2
        frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=active.n_fft)
        removals = _find_removals(events, spectrum, frequencies, sample_rate, active)
    except Exception:
        logger.warning("Harmonic evidence extraction failed for %s", audio_path, exc_info=True)
        return HarmonicEvidence.unavailable()
    return HarmonicEvidence(
        version=active.version,
        status="available",
        source="AUDIO_STFT",
        removals=removals,
    )


def _load_audio(
    audio_path: Path, config: HarmonicEvidenceConfig
) -> tuple[np.ndarray, int]:
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    audio, sample_rate = librosa.load(audio_path, sr=config.sample_rate, mono=True)
    if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-8:
        raise ValueError("audio contains no usable signal")
    return audio, sample_rate


def _find_removals(
    events: list[NoteEvent],
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> tuple[HarmonicRemoval, ...]:
    removals = []
    for candidate in sorted(events, key=_event_sort_key):
        pairs = _candidate_pairs(candidate, events, config)
        measured = [
            _measure_pair(
                fundamental,
                candidate,
                order,
                cents,
                spectrum,
                frequencies,
                sample_rate,
                config,
            )
            for fundamental, order, cents in pairs
        ]
        eligible = [
            item
            for item in measured
            if item.energy_ratio <= config.maximum_energy_ratio
            and not item.independent_onset
        ]
        if eligible:
            removals.append(min(eligible, key=lambda item: item.energy_ratio))
    return tuple(removals)


def _candidate_pairs(
    candidate: NoteEvent,
    events: list[NoteEvent],
    config: HarmonicEvidenceConfig,
) -> list[tuple[NoteEvent, int, float]]:
    pairs = []
    for fundamental in events:
        if fundamental.pitch >= candidate.pitch:
            continue
        if fundamental.start_sec > candidate.start_sec + config.onset_alignment_tolerance_seconds:
            continue
        if fundamental.end_sec < candidate.start_sec:
            continue
        frequency_ratio = 2 ** ((candidate.pitch - fundamental.pitch) / 12)
        harmonic_number = round(frequency_ratio)
        if not 2 <= harmonic_number <= config.maximum_harmonic_order:
            continue
        cents = 1200 * math.log2(frequency_ratio / harmonic_number)
        if abs(cents) <= config.tuning_tolerance_cents:
            pairs.append((fundamental, harmonic_number, cents))
    return pairs


def _measure_pair(
    fundamental: NoteEvent,
    candidate: NoteEvent,
    harmonic_number: int,
    tuning_error_cents: float,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> HarmonicRemoval:
    fundamental_energy = _band_energy(
        fundamental.pitch,
        candidate.start_sec,
        spectrum,
        frequencies,
        sample_rate,
        config,
    )
    harmonic_energy = _band_energy(
        candidate.pitch,
        candidate.start_sec,
        spectrum,
        frequencies,
        sample_rate,
        config,
    )
    onset_growth = _onset_growth(
        candidate.pitch,
        candidate.start_sec,
        spectrum,
        frequencies,
        sample_rate,
        config,
    )
    independent_onset = (
        candidate.start_sec - fundamental.start_sec
        > config.onset_alignment_tolerance_seconds
        and onset_growth >= config.minimum_independent_onset_growth
    )
    return HarmonicRemoval(
        fundamental_pitch=int(fundamental.pitch),
        harmonic_pitch=int(candidate.pitch),
        harmonic_start_sec=float(candidate.start_sec),
        harmonic_end_sec=float(candidate.end_sec),
        harmonic_number=int(harmonic_number),
        tuning_error_cents=round(tuning_error_cents, 6),
        energy_ratio=round(harmonic_energy / (fundamental_energy + 1e-12), 6),
        independent_onset=bool(independent_onset),
    )


def _band_energy(
    pitch: int,
    at_time: float,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> float:
    frequency = float(librosa.midi_to_hz(pitch))
    bin_index = int(np.argmin(np.abs(frequencies - frequency)))
    start = max(
        0,
        int(librosa.time_to_frames(at_time, sr=sample_rate, hop_length=config.hop_length)),
    )
    frame_count = max(
        1,
        round(config.onset_window_seconds * sample_rate / config.hop_length),
    )
    stop = min(spectrum.shape[1], start + frame_count)
    band = spectrum[max(0, bin_index - 1) : bin_index + 2, start:stop]
    return float(np.mean(band)) if band.size else 0.0


def _onset_growth(
    pitch: int,
    at_time: float,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> float:
    after = _band_energy(
        pitch, at_time, spectrum, frequencies, sample_rate, config
    )
    before_time = max(0.0, at_time - config.onset_window_seconds)
    before = _band_energy(
        pitch, before_time, spectrum, frequencies, sample_rate, config
    )
    return after / (before + 1e-12)


def _event_sort_key(event: NoteEvent) -> tuple[float, int, float]:
    return event.start_sec, event.pitch, event.end_sec
