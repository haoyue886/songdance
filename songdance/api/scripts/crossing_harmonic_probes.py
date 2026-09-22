"""Counterfactual WAV probes for offline harmonic-policy evaluation only."""

from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicRemoval,
    extract_harmonic_evidence,
    supports_energy_velocity_attack,
)
from app.pipeline.transcribe import NoteEvent

STRATEGIES = ("release_tracking", "strict_tracking")


def proposed_removals(pair: HarmonicRemoval) -> dict[str, bool]:
    """Unapproved hypotheses. Must not be imported by app/pipeline."""
    measurable = all(
        v is not None and np.isfinite(v)
        for v in (
            pair.onset_delta_seconds,
            pair.velocity_ratio,
            pair.duration_ratio,
            pair.energy_ratio,
            pair.release_energy_ratio,
            pair.tracking_energy_ratio,
        )
    )
    basic = bool(
        measurable
        and not pair.independent_onset
        and not pair.release_probe_blocked
        and abs(pair.onset_delta_seconds) <= 0.08
        and 0 < pair.energy_ratio <= 0.22
        and 0 < pair.velocity_ratio <= 0.85
        and 0 < pair.duration_ratio <= 1
        and pair.release_energy_ratio > 0.25
        and pair.tracking_energy_ratio >= 0.3
        and not supports_energy_velocity_attack(pair)
    )
    strict = bool(basic and pair.tracking_energy_ratio >= 0.9 and pair.velocity_ratio <= 0.6)
    return dict(zip(STRATEGIES, (basic, strict), strict=True))


def paired_wave(
    lower_pitch: int, interval: int, upper_amplitude: float, phase: float, duration: float
) -> tuple[np.ndarray, int, list[NoteEvent]]:
    rate = 22050
    times = np.arange(2 * rate) / rate
    audio = np.zeros_like(times)
    for pitch, stop, amplitude, angle in (
        (lower_pitch, 1.5, 0.8, 0),
        (lower_pitch + interval, 0.2 + duration, upper_amplitude, phase),
    ):
        relative = times - 0.2
        active = (relative >= 0) & (times < stop)
        x = relative[active]
        envelope = np.minimum(x / 0.008, 1) * np.exp(-2.6 * x)
        for partial in range(1, 7):
            audio[active] += (
                amplitude
                * envelope
                / partial**1.35
                * np.sin(2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * partial * x + angle)
            )
    # Common fixed gain across the paired conditions. FLOAT WAV avoids clipping/quantization.
    events = [
        NoteEvent(0.2, 1.2, lower_pitch, 96, 0.75),
        NoteEvent(0.2, 0.2 + duration, lower_pitch + interval, 53, 0.416),
    ]
    return audio * 0.5, rate, events


def measure_probe(
    path: Path,
    *,
    lower_pitch: int,
    interval: int,
    upper_amplitude: float,
    phase: float,
    duration: float,
) -> tuple[dict[str, object], list[NoteEvent], HarmonicEvidence]:
    audio, rate, events = paired_wave(lower_pitch, interval, upper_amplitude, phase, duration)
    sf.write(path, audio, rate, subtype="FLOAT")
    evidence = extract_harmonic_evidence(path, events)
    if evidence.status != "available":
        raise RuntimeError("harmonic probe evidence unavailable")
    pair = next(
        (
            p
            for p in (*evidence.observations, *evidence.removals)
            if p.matches(events[1]) and p.fundamental_pitch == lower_pitch
        ),
        None,
    )
    decisions = proposed_removals(pair) if pair else {name: False for name in STRATEGIES}
    return (
        {
            "parameters": {
                "lower_pitch": lower_pitch,
                "interval": interval,
                "upper_amplitude": upper_amplitude,
                "phase": phase,
                "duration": duration,
            },
            "truth": "real_simultaneous_note" if upper_amplitude > 0 else "natural_partial_only",
            "candidate_events": [asdict(e) for e in events],
            "measurement": pair.summary() if pair else None,
            "proposed_removals": decisions,
            "evidence_status": evidence.status,
            "label_source": "controlled_additive_waveform",
            "event_source": "postprocess_test_hypotheses_not_model_inference",
        },
        events,
        evidence,
    )
