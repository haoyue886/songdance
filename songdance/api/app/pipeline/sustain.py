import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median

import librosa
import numpy as np
import pretty_midi

SUSTAIN_EVIDENCE_VERSION = "sustain-evidence-v1"
AUDIO_ONSET_RESONANCE = "AUDIO_ONSET_RESONANCE"
AUDIO_SUSTAIN_PEDAL = "AUDIO_SUSTAIN_PEDAL"
MIDI_CC64 = "MIDI_CC64"
SUSTAIN_EVIDENCE_UNAVAILABLE = "SUSTAIN_EVIDENCE_UNAVAILABLE"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SustainEvidenceConfig:
    sample_rate: int = 22_050
    hop_length: int = 512
    minimum_resonance_ratio: float = 0.08
    minimum_audio_pedal_onsets: int = 8
    maximum_audio_pedal_gap_seconds: float = 0.35
    maximum_audio_pedal_break_seconds: float = 0.08

    @property
    def version(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
        return f"{SUSTAIN_EVIDENCE_VERSION}/{digest}"


@dataclass(frozen=True)
class SustainEvidence:
    version: str
    status: str
    sources: tuple[str, ...]
    independent_onset_seconds: tuple[float, ...]
    resonant_intervals: tuple[tuple[float, float], ...]
    cc64_intervals: tuple[tuple[float, float], ...]
    audio_pedal_intervals: tuple[tuple[float, float], ...] = ()

    @classmethod
    def unavailable(cls) -> "SustainEvidence":
        return cls(
            version=SustainEvidenceConfig().version,
            status="unavailable",
            sources=(),
            independent_onset_seconds=(),
            resonant_intervals=(),
            cc64_intervals=(),
            audio_pedal_intervals=(),
        )

    def summary(self) -> dict[str, object]:
        return {
            "version": self.version,
            "status": self.status,
            "sources": self.sources,
            "independent_onset_count": len(self.independent_onset_seconds),
            "resonant_interval_count": len(self.resonant_intervals),
            "cc64_interval_count": len(self.cc64_intervals),
            "audio_pedal_interval_count": len(self.audio_pedal_intervals),
        }


def extract_sustain_evidence(
    audio_path: Path,
    raw_midi: pretty_midi.PrettyMIDI,
    config: SustainEvidenceConfig | None = None,
) -> SustainEvidence:
    active = config or SustainEvidenceConfig()
    cc64 = _cc64_intervals(raw_midi)
    try:
        if not audio_path.is_file():
            raise FileNotFoundError(audio_path)
        audio, sample_rate = librosa.load(audio_path, sr=active.sample_rate, mono=True)
        if audio.size == 0 or float(np.max(np.abs(audio))) < 1e-8:
            raise ValueError("audio contains no usable signal")
        onset_envelope = librosa.onset.onset_strength(
            y=audio, sr=sample_rate, hop_length=active.hop_length
        )
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            hop_length=active.hop_length,
            units="frames",
            normalize=True,
        )
        onset_seconds = tuple(
            round(float(value), 6)
            for value in librosa.frames_to_time(
                onset_frames, sr=sample_rate, hop_length=active.hop_length
            )
        )
        rms = librosa.feature.rms(y=audio, hop_length=active.hop_length)[0]
        resonant = _resonant_intervals(
            onset_frames, onset_seconds, rms, active.minimum_resonance_ratio
        )
    except Exception:
        logger.warning("Sustain evidence extraction failed for %s", audio_path, exc_info=True)
        onset_seconds = tuple(
            sorted(
                {
                    round(note.start, 6)
                    for instrument in raw_midi.instruments
                    for note in instrument.notes
                }
            )
        )
        resonant = ()
    audio_pedal = infer_audio_pedal_intervals(resonant, active)
    sources = []
    if resonant:
        sources.append(AUDIO_ONSET_RESONANCE)
    if audio_pedal:
        sources.append(AUDIO_SUSTAIN_PEDAL)
    if cc64:
        sources.append(MIDI_CC64)
    return SustainEvidence(
        version=active.version,
        status="available" if sources else "unavailable",
        sources=tuple(sources),
        independent_onset_seconds=onset_seconds if sources else (),
        resonant_intervals=resonant,
        cc64_intervals=cc64,
        audio_pedal_intervals=audio_pedal,
    )


def infer_audio_pedal_intervals(
    intervals: tuple[tuple[float, float], ...],
    config: SustainEvidenceConfig | None = None,
) -> tuple[tuple[float, float], ...]:
    active = config or SustainEvidenceConfig()
    required_interval_count = active.minimum_audio_pedal_onsets - 1
    if len(intervals) < required_interval_count:
        return ()
    onset_gaps = tuple(
        right[0] - left[0] for left, right in zip(intervals, intervals[1:], strict=False)
    )
    if not onset_gaps or median(onset_gaps) > active.maximum_audio_pedal_gap_seconds:
        return ()
    runs: list[tuple[float, float, int]] = []
    start, end = intervals[0]
    count = 1
    for next_start, next_end in intervals[1:]:
        if next_start <= end + active.maximum_audio_pedal_break_seconds:
            end = max(end, next_end)
            count += 1
            continue
        if count >= required_interval_count:
            runs.append((start, end, count))
        start, end, count = next_start, next_end, 1
    if count >= required_interval_count:
        runs.append((start, end, count))
    return tuple((start, end) for start, end, _ in runs)


def _resonant_intervals(
    onset_frames: np.ndarray,
    onset_seconds: tuple[float, ...],
    rms: np.ndarray,
    minimum_ratio: float,
) -> tuple[tuple[float, float], ...]:
    if len(onset_frames) < 2:
        return ()
    peak = float(np.max(rms)) or 1.0
    intervals = []
    for index, (left, right) in enumerate(zip(onset_frames, onset_frames[1:], strict=False)):
        if right - left < 2:
            continue
        tail_start = left + max(1, (right - left) // 2)
        tail = rms[tail_start:right]
        if tail.size and float(np.mean(tail)) / peak >= minimum_ratio:
            intervals.append((onset_seconds[index], onset_seconds[index + 1]))
    return tuple(intervals)


def _cc64_intervals(midi: pretty_midi.PrettyMIDI) -> tuple[tuple[float, float], ...]:
    intervals = []
    midi_end = midi.get_end_time()
    for instrument in midi.instruments:
        controls = sorted(
            (item for item in instrument.control_changes if item.number == 64),
            key=lambda item: item.time,
        )
        pressed_at = None
        for control in controls:
            if control.value >= 64 and pressed_at is None:
                pressed_at = control.time
            elif control.value < 64 and pressed_at is not None:
                intervals.append((round(pressed_at, 6), round(control.time, 6)))
                pressed_at = None
        if pressed_at is not None and midi_end > pressed_at:
            intervals.append((round(pressed_at, 6), round(midi_end, 6)))
    return _merge_intervals(intervals)


def _merge_intervals(
    intervals: list[tuple[float, float]],
) -> tuple[tuple[float, float], ...]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(merged)
