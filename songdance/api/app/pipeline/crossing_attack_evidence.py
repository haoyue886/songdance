"""Separate nearby tones before looking for a short re-strike of the candidate pitch."""

from dataclasses import replace
from functools import lru_cache
from statistics import median
from typing import TYPE_CHECKING

import numpy as np

from app.pipeline.transcribe import NoteEvent

if TYPE_CHECKING:
    from app.pipeline.harmonics import NoteOnsetEvidence

WINDOW_SECONDS = 0.064
CENTERS = (-0.17, -0.13, -0.09, -0.04, 0.04, 0.06)
MAX_CONDITION_NUMBER = 100


def transient_fit_error(
    audio: np.ndarray,
    rate: int,
    event: NoteEvent,
    events: list[NoteEvent],
    *,
    attack_sec: float | None = None,
) -> float | None:
    frequency = 440 * 2 ** ((event.pitch - 69) / 12)
    start = event.start_sec if attack_sec is None else attack_sec
    if start < 0.35 or start + 0.2 >= len(audio) / rate:
        return None
    neighbors = {
        e.pitch
        for e in events
        if e.pitch != event.pitch and e.start_sec < start + 0.12 and e.end_sec > start - 0.25
    }
    nuisance = sorted(
        {
            440 * 2 ** ((p - 69) / 12) * h
            for p in {event.pitch, *neighbors}
            for h in range(1, 7)
            if not (p == event.pitch and h == 1) and 440 * 2 ** ((p - 69) / 12) * h < rate / 2 - 25
        }
    )
    # Near-unisons with another fundamental/partial cannot be resolved reliably.
    if frequency >= rate / 2 - 25 or any(abs(f - frequency) < 15 for f in nuisance):
        return None
    carriers = [frequency]
    for value in nuisance:
        if min(abs(value - existing) for existing in carriers) > 10:
            carriers.append(value)
    estimator = _estimator(tuple(carriers), rate)
    if estimator is None:
        return None
    count = estimator.shape[1]
    coefficients = []
    for center in CENTERS:
        left = round((start + center) * rate) - count // 2
        right = left + count
        if left < 0 or right > len(audio):
            return None
        cosine, sine = estimator @ audio[left:right]
        coefficients.append(
            (cosine - 1j * sine) * np.exp(-2j * np.pi * frequency * (left + count / 2) / rate)
        )
    values, times = np.asarray(coefficients), np.asarray(CENTERS)
    before, early = times < -0.08, times >= -0.04
    if np.median(np.abs(values[before])) < 1e-5:
        return None
    logs = np.log(np.maximum(np.abs(values), 1e-10))
    slope, intercept = np.polyfit(times[before], logs[before], 1)
    if slope >= 0:
        return None
    phases = np.unwrap(np.angle(values))
    phase_slope, phase_intercept = np.polyfit(times[before], phases[before], 1)
    amplitude_error = np.abs(logs[early] - (slope * times[early] + intercept))
    phase_residual = phases[early] - (phase_slope * times[early] + phase_intercept)
    phase_error = np.abs(np.angle(np.exp(1j * phase_residual)))
    return round(float(max(np.max(amplitude_error), np.max(phase_error))), 6)


@lru_cache(maxsize=32)
def _estimator(carriers: tuple[float, ...], rate: int) -> np.ndarray | None:
    """Only cache the small signal-independent projection, never audio or event state."""
    count = round(WINDOW_SECONDS * rate)
    relative = (np.arange(count) - count / 2) / rate
    columns = []
    for value in carriers:
        phase = 2 * np.pi * value * relative
        cosine, sine = np.cos(phase), np.sin(phase)
        # Local linear envelopes model the other hand's changing amplitude.
        columns.extend(
            (cosine, sine, cosine * relative / WINDOW_SECONDS, sine * relative / WINDOW_SECONDS)
        )
    basis = np.stack(columns, axis=1)
    if basis.shape[1] >= basis.shape[0]:
        return None
    left, singular, right = np.linalg.svd(basis, full_matrices=False)
    if singular[-1] <= 0 or singular[0] / singular[-1] > MAX_CONDITION_NUMBER:
        return None
    result = (right.T[:2] / singular) @ left.T
    result.setflags(write=False)
    return result


def measure_transients(
    audio: np.ndarray,
    rate: int,
    events: list[NoteEvent],
    observations: tuple["NoteOnsetEvidence", ...],
) -> tuple["NoteOnsetEvidence", ...]:
    measured = []
    for observation in observations:
        anchors = [
            o.start_sec
            for o in observations
            if o.pitch != observation.pitch
            and o.independent_onset
            and abs(o.start_sec - observation.start_sec) <= 0.08
        ]
        if observation.independent_onset or not anchors:
            measured.append(observation)
            continue
        # Tail segmentation can lag the physical attack. Use its simultaneously struck neighbor.
        anchor = median(anchors)
        event = NoteEvent(observation.start_sec, observation.end_sec, observation.pitch, 1, 0)
        candidate_error = transient_fit_error(audio, rate, event, events)
        neighbor_error = transient_fit_error(audio, rate, event, events, attack_sec=anchor)
        error = (
            max(candidate_error, neighbor_error)
            if candidate_error is not None and neighbor_error is not None
            else None
        )
        measured.append(
            replace(
                observation,
                transient_fit_error=error,
                transient_reference_sec=anchor,
            )
        )
    return tuple(measured)
