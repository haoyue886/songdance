import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import librosa
import numpy as np

from app.pipeline.transcribe import NoteEvent

HARMONIC_EVIDENCE_VERSION = "harmonic-evidence-v4"
HARMONIC_AUDIO_EVIDENCE = "HARMONIC_AUDIO_EVIDENCE"
HARMONIC_BASS_FUNDAMENTAL_EVIDENCE = "HARMONIC_BASS_FUNDAMENTAL_EVIDENCE"
MINIMUM_NOTE_ENERGY_VELOCITY_COHERENCE = 0.4
MAXIMUM_NOTE_ENERGY_VELOCITY_COHERENCE = 1.25
MINIMUM_RAW_NOTE_ENERGY_VELOCITY_COHERENCE = 0.32
MAXIMUM_INDEPENDENT_RELEASE_ENERGY_RATIO = 0.25
MINIMUM_HARMONIC_TRACKING_RATIO = 0.3
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HarmonicEvidenceConfig:
    sample_rate: int = 22_050
    hop_length: int = 256
    n_fft: int = 4096
    maximum_harmonic_order: int = 6
    tuning_tolerance_cents: float = 35.0
    maximum_energy_ratio: float = 0.22
    maximum_velocity_ratio: float = 0.85
    maximum_duration_ratio: float = 2.1
    bass_priority_enabled: bool = False
    bass_priority_source: str | None = None
    bass_fundamental_max_pitch: int = 60
    bass_priority_harmonic_order: int = 2
    bass_maximum_energy_ratio: float = 0.75
    bass_maximum_velocity_ratio: float = 0.55
    bass_maximum_duration_ratio: float = 1.0
    onset_alignment_tolerance_seconds: float = 0.08
    onset_window_seconds: float = 0.08
    minimum_independent_onset_growth: float = 2.0
    release_probe_window_seconds: float = 0.02
    release_probe_offset_seconds: float = 0.04
    maximum_release_noise_floor_ratio: float = 0.1
    minimum_harmonic_tracking_ratio: float = MINIMUM_HARMONIC_TRACKING_RATIO

    def __post_init__(self) -> None:
        if self.bass_priority_enabled and self.bass_priority_source is None:
            raise ValueError("bass harmonic priority requires an evidence source")
        if not self.bass_priority_enabled and self.bass_priority_source is not None:
            raise ValueError("bass harmonic evidence source requires enabled priority")

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
    onset_growth: float | None = None
    reason: str = HARMONIC_AUDIO_EVIDENCE
    fundamental_start_sec: float | None = None
    fundamental_end_sec: float | None = None
    fundamental_velocity: int | None = None
    harmonic_velocity: int | None = None
    onset_delta_seconds: float | None = None
    velocity_ratio: float | None = None
    duration_ratio: float | None = None
    release_energy_ratio: float | None = None
    tracking_energy_ratio: float | None = None
    tracking_threshold: float = MINIMUM_HARMONIC_TRACKING_RATIO
    release_probe_blocked: bool = False
    decision_source: str = "audio_stft"

    def summary(self) -> dict[str, object]:
        return asdict(self)

    def matches(self, event: NoteEvent) -> bool:
        return (
            event.pitch == self.harmonic_pitch
            and event.start_sec == self.harmonic_start_sec
            and event.end_sec == self.harmonic_end_sec
        )


@dataclass(frozen=True)
class NoteOnsetEvidence:
    pitch: int
    start_sec: float
    end_sec: float
    onset_growth: float
    independent_onset: bool
    pre_onset_energy: float | None = None
    onset_energy: float | None = None
    decay_fit_error: float | None = None
    transient_fit_error: float | None = None
    transient_reference_sec: float | None = None

    def summary(self) -> dict[str, object]:
        return asdict(self)

    def matches(self, event: NoteEvent, *, tolerance_seconds: float = 0.08) -> bool:
        return (
            event.pitch == self.pitch and abs(event.start_sec - self.start_sec) <= tolerance_seconds
        )


@dataclass(frozen=True)
class HarmonicEvidence:
    version: str
    status: str
    source: str | None
    removals: tuple[HarmonicRemoval, ...]
    observations: tuple[HarmonicRemoval, ...] = ()
    onset_observations: tuple[NoteOnsetEvidence, ...] = ()

    @classmethod
    def unavailable(cls) -> "HarmonicEvidence":
        return cls(
            version=HarmonicEvidenceConfig().version,
            status="unavailable",
            source=None,
            removals=(),
            observations=(),
            onset_observations=(),
        )

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "source": self.source,
            "removed_candidate_count": len(self.removals),
            "removals": [item.summary() for item in self.removals],
            "observed_pair_count": len(self.observations),
            "observations": [item.summary() for item in self.observations],
            "observed_onset_count": len(self.onset_observations),
            "onset_observations": [item.summary() for item in self.onset_observations],
        }


def extract_harmonic_evidence(
    audio_path: Path,
    events: list[NoteEvent],
    config: HarmonicEvidenceConfig | None = None,
    *,
    include_decay_evidence: bool = False,
    include_transient_evidence: bool = False,
) -> HarmonicEvidence:
    active = config or HarmonicEvidenceConfig()
    try:
        audio, sample_rate = _load_audio(audio_path, active)
        spectrum = (
            np.abs(
                librosa.stft(
                    audio,
                    n_fft=active.n_fft,
                    hop_length=active.hop_length,
                    window="hann",
                )
            )
            ** 2
        )
        frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=active.n_fft)
        removals, observations = _find_removals(
            events, audio, spectrum, frequencies, sample_rate, active
        )
        onset_observations = _measure_onsets(events, spectrum, frequencies, sample_rate, active)
        if include_decay_evidence:
            from app.pipeline.onset_decay import decay_fit_error

            onset_observations = tuple(
                replace(o, decay_fit_error=decay_fit_error(audio, sample_rate, e))
                if not o.independent_onset else o
                for e, o in zip(
                    sorted(events, key=_event_sort_key), onset_observations, strict=True
                )
            )
        if include_transient_evidence:
            from app.pipeline.crossing_attack_evidence import measure_transients

            onset_observations = measure_transients(
                audio, sample_rate, events, onset_observations
            )
    except Exception:
        logger.warning("Harmonic evidence extraction failed for %s", audio_path, exc_info=True)
        return HarmonicEvidence.unavailable()
    return HarmonicEvidence(
        version=active.version,
        status="available",
        source="AUDIO_STFT",
        removals=removals,
        observations=observations,
        onset_observations=onset_observations,
    )


def _load_audio(audio_path: Path, config: HarmonicEvidenceConfig) -> tuple[np.ndarray, int]:
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)
    audio, sample_rate = librosa.load(audio_path, sr=config.sample_rate, mono=True)
    if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-8:
        raise ValueError("audio contains no usable signal")
    return audio, sample_rate


def _find_removals(
    events: list[NoteEvent],
    audio: np.ndarray,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> tuple[tuple[HarmonicRemoval, ...], tuple[HarmonicRemoval, ...]]:
    removals = []
    observations = []
    for candidate in sorted(events, key=_event_sort_key):
        pairs = _candidate_pairs(candidate, events, config)
        measured = [
            (
                fundamental,
                _measure_pair(
                    fundamental,
                    candidate,
                    order,
                    cents,
                    audio,
                    events,
                    spectrum,
                    frequencies,
                    sample_rate,
                    config,
                ),
            )
            for fundamental, order, cents in pairs
        ]
        eligible = []
        for fundamental, item in measured:
            if _plausible_harmonic_observation(item, config):
                observations.append(item)
            if item.release_energy_ratio is None:
                continue
            simultaneous_attack = supports_independent_simultaneous_attack(
                item,
                onset_tolerance_seconds=config.onset_alignment_tolerance_seconds,
            )
            if item.release_probe_blocked:
                continue
            if simultaneous_attack and not (
                config.bass_priority_enabled
                and fundamental.pitch <= config.bass_fundamental_max_pitch
            ):
                continue
            if (
                fundamental.pitch <= config.bass_fundamental_max_pitch
                and not config.bass_priority_enabled
            ):
                continue
            if item.energy_ratio <= config.maximum_energy_ratio:
                if not _relative_harmonic_event_evidence(item, config):
                    continue
                if (
                    fundamental.pitch <= config.bass_fundamental_max_pitch
                    and not _bass_relative_event_evidence(fundamental, candidate, config)
                ):
                    continue
                eligible.append(
                    replace(
                        item,
                        reason=(
                            HARMONIC_BASS_FUNDAMENTAL_EVIDENCE
                            if fundamental.pitch <= config.bass_fundamental_max_pitch
                            else item.reason
                        ),
                        decision_source=(
                            config.bass_priority_source
                            if fundamental.pitch <= config.bass_fundamental_max_pitch
                            else item.decision_source
                        ),
                    )
                )
            elif _bass_fundamental_priority(fundamental, candidate, item, config):
                eligible.append(
                    replace(
                        item,
                        reason=HARMONIC_BASS_FUNDAMENTAL_EVIDENCE,
                        decision_source=config.bass_priority_source or "unknown",
                    )
                )
        if eligible:
            removals.append(min(eligible, key=lambda item: item.energy_ratio))
    return tuple(removals), tuple(observations)


def _plausible_harmonic_observation(item: HarmonicRemoval, config: HarmonicEvidenceConfig) -> bool:
    return (
        not item.independent_onset
        and item.energy_ratio <= config.bass_maximum_energy_ratio
        and _relative_harmonic_event_evidence(item, config)
    )


def _relative_harmonic_event_evidence(
    item: HarmonicRemoval, config: HarmonicEvidenceConfig
) -> bool:
    return (
        item.velocity_ratio is not None
        and item.velocity_ratio <= config.maximum_velocity_ratio
        and item.duration_ratio is not None
        and item.duration_ratio <= config.maximum_duration_ratio
    )


def _measure_onsets(
    events: list[NoteEvent],
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> tuple[NoteOnsetEvidence, ...]:
    observations = []
    for event in sorted(events, key=_event_sort_key):
        pre_onset_energy, onset_energy = _onset_energies(
            event.pitch,
            event.start_sec,
            spectrum,
            frequencies,
            sample_rate,
            config,
        )
        growth = onset_energy / (pre_onset_energy + 1e-12)
        observations.append(
            NoteOnsetEvidence(
                pitch=event.pitch,
                start_sec=event.start_sec,
                end_sec=event.end_sec,
                onset_growth=round(growth, 6),
                independent_onset=growth >= config.minimum_independent_onset_growth,
                pre_onset_energy=round(pre_onset_energy, 6),
                onset_energy=round(onset_energy, 6),
            )
        )
    return tuple(observations)


def _bass_fundamental_priority(
    fundamental: NoteEvent,
    candidate: NoteEvent,
    measurement: HarmonicRemoval,
    config: HarmonicEvidenceConfig,
) -> bool:
    return (
        config.bass_priority_enabled
        and fundamental.pitch <= config.bass_fundamental_max_pitch
        and measurement.harmonic_number == config.bass_priority_harmonic_order
        and measurement.energy_ratio <= config.bass_maximum_energy_ratio
        and _bass_relative_event_evidence(fundamental, candidate, config)
    )


def _bass_relative_event_evidence(
    fundamental: NoteEvent,
    candidate: NoteEvent,
    config: HarmonicEvidenceConfig,
) -> bool:
    fundamental_duration = fundamental.end_sec - fundamental.start_sec
    candidate_duration = candidate.end_sec - candidate.start_sec
    return (
        abs(candidate.start_sec - fundamental.start_sec) <= config.onset_alignment_tolerance_seconds
        and candidate.velocity <= fundamental.velocity * config.bass_maximum_velocity_ratio
        and candidate_duration <= fundamental_duration * config.bass_maximum_duration_ratio
    )


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
    audio: np.ndarray,
    events: list[NoteEvent],
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
        candidate.start_sec - fundamental.start_sec > config.onset_alignment_tolerance_seconds
        and onset_growth >= config.minimum_independent_onset_growth
    )
    fundamental_duration = fundamental.end_sec - fundamental.start_sec
    harmonic_duration = candidate.end_sec - candidate.start_sec
    release_energy_ratio, release_probe_blocked = _release_energy_ratio(
        fundamental,
        candidate,
        audio,
        events,
        sample_rate,
        config,
    )
    tracking_energy_ratio = _harmonic_tracking_ratio(
        fundamental,
        candidate,
        spectrum,
        frequencies,
        sample_rate,
        config,
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
        onset_growth=round(onset_growth, 6),
        fundamental_start_sec=float(fundamental.start_sec),
        fundamental_end_sec=float(fundamental.end_sec),
        fundamental_velocity=int(fundamental.velocity),
        harmonic_velocity=int(candidate.velocity),
        onset_delta_seconds=round(candidate.start_sec - fundamental.start_sec, 6),
        velocity_ratio=round(candidate.velocity / max(fundamental.velocity, 1), 6),
        duration_ratio=round(harmonic_duration / max(fundamental_duration, 1e-12), 6),
        release_energy_ratio=(
            round(release_energy_ratio, 6) if release_energy_ratio is not None else None
        ),
        tracking_energy_ratio=(
            round(tracking_energy_ratio, 6) if tracking_energy_ratio is not None else None
        ),
        tracking_threshold=config.minimum_harmonic_tracking_ratio,
        release_probe_blocked=release_probe_blocked,
    )


def _harmonic_tracking_ratio(
    fundamental: NoteEvent,
    candidate: NoteEvent,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> float | None:
    duration = candidate.end_sec - candidate.start_sec
    active_time = candidate.start_sec + min(duration * 0.5, duration - 0.04)
    released_time = candidate.end_sec + config.release_probe_offset_seconds
    spectrum_duration = spectrum.shape[1] * config.hop_length / sample_rate
    if active_time <= candidate.start_sec or released_time >= spectrum_duration:
        return None
    fundamental_active = _band_energy(
        fundamental.pitch, active_time, spectrum, frequencies, sample_rate, config
    )
    fundamental_released = _band_energy(
        fundamental.pitch, released_time, spectrum, frequencies, sample_rate, config
    )
    if fundamental_active <= 1e-12 or fundamental_released < fundamental_active * 0.05:
        return None
    harmonic_active = _band_energy(
        candidate.pitch, active_time, spectrum, frequencies, sample_rate, config
    )
    harmonic_released = _band_energy(
        candidate.pitch, released_time, spectrum, frequencies, sample_rate, config
    )
    active_ratio = harmonic_active / fundamental_active
    released_ratio = harmonic_released / fundamental_released
    return released_ratio / max(active_ratio, 1e-12)


def _release_energy_ratio(
    fundamental: NoteEvent,
    candidate: NoteEvent,
    audio: np.ndarray,
    events: list[NoteEvent],
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> tuple[float | None, bool]:
    window_seconds = config.release_probe_window_seconds
    candidate_duration = candidate.end_sec - candidate.start_sec
    if candidate_duration < window_seconds * 2:
        return None, False

    active_offset = max(
        window_seconds,
        min(candidate_duration * 0.5, candidate_duration - window_seconds / 2),
    )
    active_center = candidate.start_sec + active_offset
    noise_center = candidate.start_sec - config.release_probe_offset_seconds
    released_center = candidate.end_sec + config.release_probe_offset_seconds
    released_stop = released_center + window_seconds / 2
    if fundamental.end_sec < released_stop:
        return None, False

    probe_intervals = (
        (noise_center - window_seconds / 2, noise_center + window_seconds / 2),
        (released_center - window_seconds / 2, released_stop),
    )
    if any(
        event is not candidate
        and event.pitch == candidate.pitch
        and any(event.start_sec < stop and event.end_sec > start for start, stop in probe_intervals)
        for event in events
    ):
        return None, True

    noise_energy = _tone_window_energy(
        audio,
        sample_rate,
        candidate.pitch,
        noise_center,
        window_seconds,
    )
    active_energy = _tone_window_energy(
        audio,
        sample_rate,
        candidate.pitch,
        active_center,
        window_seconds,
    )
    released_energy = _tone_window_energy(
        audio,
        sample_rate,
        candidate.pitch,
        released_center,
        window_seconds,
    )
    if noise_energy is None or active_energy is None or released_energy is None:
        return None, False
    if noise_energy >= active_energy * config.maximum_release_noise_floor_ratio:
        return None, True
    active_excess = max(0.0, active_energy - noise_energy)
    released_excess = max(0.0, released_energy - noise_energy)
    if active_excess <= 1e-12:
        return None, False
    return released_excess / active_excess, False


def supports_independent_simultaneous_attack(
    measurement: HarmonicRemoval,
    *,
    onset_tolerance_seconds: float = 0.08,
) -> bool:
    if measurement.release_energy_ratio is None:
        return False
    return (
        supports_energy_velocity_attack(
            measurement,
            onset_tolerance_seconds=onset_tolerance_seconds,
        )
        and measurement.release_energy_ratio <= MAXIMUM_INDEPENDENT_RELEASE_ENERGY_RATIO
    )


def supports_energy_velocity_attack(
    measurement: HarmonicRemoval,
    *,
    onset_tolerance_seconds: float = 0.08,
) -> bool:
    onset_delta = measurement.onset_delta_seconds
    velocity_ratio = measurement.velocity_ratio or 0.0
    duration_ratio = min(measurement.duration_ratio or 1.0, 1.0)
    raw_coherence = measurement.energy_ratio / max(velocity_ratio**2, 1e-12)
    duration_coherence = measurement.energy_ratio / max(
        velocity_ratio**2 * duration_ratio,
        1e-12,
    )
    return (
        onset_delta is not None
        and abs(onset_delta) <= onset_tolerance_seconds
        and raw_coherence >= MINIMUM_RAW_NOTE_ENERGY_VELOCITY_COHERENCE
        and MINIMUM_NOTE_ENERGY_VELOCITY_COHERENCE
        <= duration_coherence
        <= MAXIMUM_NOTE_ENERGY_VELOCITY_COHERENCE
    )


def _tone_window_energy(
    audio: np.ndarray,
    sample_rate: int,
    pitch: int,
    center_time: float,
    window_seconds: float,
) -> float | None:
    sample_count = max(4, round(window_seconds * sample_rate))
    start = round((center_time - window_seconds / 2) * sample_rate)
    stop = start + sample_count
    if start < 0 or stop > audio.size:
        return None
    samples = audio[start:stop]
    window = np.hanning(sample_count)
    normalization = float(np.sum(window))
    if normalization <= 0:
        return None
    frequency = float(librosa.midi_to_hz(pitch))
    times = np.arange(sample_count) / sample_rate
    coefficient = np.sum(samples * window * np.exp(-2j * np.pi * frequency * times))
    return float(abs(coefficient / normalization) ** 2)


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
    before, after = _onset_energies(
        pitch,
        at_time,
        spectrum,
        frequencies,
        sample_rate,
        config,
    )
    return after / (before + 1e-12)


def _onset_energies(
    pitch: int,
    at_time: float,
    spectrum: np.ndarray,
    frequencies: np.ndarray,
    sample_rate: int,
    config: HarmonicEvidenceConfig,
) -> tuple[float, float]:
    after = _band_energy(pitch, at_time, spectrum, frequencies, sample_rate, config)
    before_time = max(0.0, at_time - config.onset_window_seconds)
    before = _band_energy(pitch, before_time, spectrum, frequencies, sample_rate, config)
    return before, after


def _event_sort_key(event: NoteEvent) -> tuple[float, int, float]:
    return event.start_sec, event.pitch, event.end_sec
