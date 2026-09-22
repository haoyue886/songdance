"""Check whether a candidate's fundamental follows an uninterrupted decay."""

import numpy as np
from scipy.ndimage import gaussian_filter1d

from app.pipeline.transcribe import NoteEvent


def decay_fit_error(audio: np.ndarray, rate: int, event: NoteEvent) -> float | None:
    frequency = 440 * 2 ** ((event.pitch - 69) / 12)
    start = event.start_sec
    if start < 0.35 or start + 0.2 >= len(audio) / rate or frequency >= rate / 2 - 25:
        return None
    left, right = max(0, int((start - 1) * rate)), min(len(audio), int((start + 1) * rate))
    carrier = np.exp(-2j * np.pi * frequency * np.arange(right - left) / rate)
    signal = gaussian_filter1d(audio[left:right] * carrier, 0.02 * rate)
    envelope = np.abs(signal)
    times = np.arange(len(envelope)) / rate + left / rate - start
    before = (times >= -0.2) & (times <= -0.08)
    # Ignore the other pitch's broadband attack; inspect the remaining tail instead.
    after = (times >= 0.06) & (times <= 0.18)
    if np.median(envelope[before]) < 1e-5:
        return None
    logs = np.log(np.maximum(envelope, 1e-10))
    slope, intercept = np.polyfit(times[before], logs[before], 1)
    if slope >= 0:
        return None
    residual = np.abs(logs[after] - (slope * times[after] + intercept))
    # A re-strike can change phase while leaving the envelope nearly unchanged.
    phases = np.unwrap(np.angle(signal))
    phase_slope, phase_intercept = np.polyfit(times[before], phases[before], 1)
    phase_error = phases[after] - (phase_slope * times[after] + phase_intercept)
    wrapped_error = np.abs(np.angle(np.exp(1j * phase_error)))
    return round(float(max(np.quantile(residual, 0.9), np.quantile(wrapped_error, 0.9))), 6)
