"""Correct frame-quantized constant beat grids, abstaining on variable timing."""

import math

import numpy as np

VERSION = "stable-beat-grid-v1"


def calibrate(bpm: float, times, frame_seconds: float):
    beats = np.asarray(times, dtype=float)
    audit = {
        "version": VERSION,
        "status": "retained",
        "original_bpm": float(bpm),
        "original_beats": beats.tolist(),
    }

    def retain(reason):
        return bpm, beats, {**audit, "reason": reason}

    if (
        not math.isfinite(bpm)
        or bpm <= 0
        or not math.isfinite(frame_seconds)
        or frame_seconds <= 0
        or len(beats) < 12
        or not np.all(np.isfinite(beats))
    ):
        return retain("insufficient_or_invalid_input")
    gaps = np.diff(beats)
    if np.any(gaps <= 0) or beats[-1] - beats[0] < 6:
        return retain("insufficient_or_invalid_span")
    indices = np.arange(len(beats), dtype=float)
    slope, intercept = np.polyfit(indices, beats, 1)
    fitted = intercept + slope * indices
    if slope <= 0 or fitted[0] < 0:
        return retain("invalid_fit")
    maximum_error = float(np.max(np.abs(fitted - beats)))
    half = len(beats) // 2
    first = np.polyfit(indices[:half], beats[:half], 1)[0]
    last = np.polyfit(indices[half:], beats[half:], 1)[0]
    audit.update(
        maximum_residual_seconds=maximum_error,
        half_tempo_difference_ratio=float(abs(first - last) / slope),
    )
    if (
        maximum_error > frame_seconds
        or np.max(np.abs(gaps - slope)) > 2 * frame_seconds
        or abs(first - last) / slope > 0.01
    ):
        return retain("variable_or_inconsistent_beats")
    corrected = 60 / float(slope)
    if abs(corrected - bpm) / bpm > 0.05:
        return retain("tempo_disagreement")
    return (
        corrected,
        fitted,
        {
            **audit,
            "status": "calibrated",
            "reason": "frame_quantized_stable_beats",
            "calibrated_bpm": corrected,
            "interval_seconds": float(slope),
        },
    )
