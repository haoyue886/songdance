"""Offline spectral attribution evidence. Frequency overlap never authorizes deletion."""

from math import ceil, log2

import numpy as np

from app.pipeline.transcribe import NoteEvent

TUNING_CENTS = 35.0
PARTIALS = 6
MIN_WINDOW_SECONDS = 0.06
MAX_WINDOW_SECONDS = 0.30


def _frequency(pitch: int) -> float:
    return 440 * 2 ** ((pitch - 69) / 12)


def _interval(frequency: float, resolution: float) -> tuple[float, float]:
    ratio = 2 ** (TUNING_CENTS / 1200)
    # A Hann main lobe extends about two unpadded frequency bins on either side.
    return frequency / ratio - 2 * resolution, frequency * ratio + 2 * resolution


def measure_spectral_family(
    audio: np.ndarray,
    rate: int,
    event: NoteEvent,
    events: list[NoteEvent],
    *,
    padding_factor: int = 8,
) -> dict[str, object]:
    if rate <= 0 or padding_factor < 1:
        raise ValueError("positive sample rate and padding factor required")
    if audio.ndim != 1 or not np.all(np.isfinite(audio)):
        raise ValueError("finite mono audio required")
    if _frequency(event.pitch) >= rate / 2:
        return {
            "status": "insufficient_bandwidth",
            "decision": "retain",
            "partials": [],
            "independent_attack_confirmed": False,
        }
    start = event.start_sec + 0.02
    end = min(event.end_sec, start + MAX_WINDOW_SECONDS, len(audio) / rate)
    left, right = max(0, round(start * rate)), min(len(audio), round(end * rate))
    count = right - left
    if count < rate * MIN_WINDOW_SECONDS:
        return {
            "status": "insufficient_window",
            "decision": "retain",
            "partials": [],
            "independent_attack_confirmed": False,
        }
    samples = audio[left:right]
    window = np.hanning(count)
    size = 2 ** ceil(log2(count * padding_factor))
    amplitude = np.abs(np.fft.rfft(samples * window, size)) * 2 / window.sum()
    frequencies = np.fft.rfftfreq(size, 1 / rate)
    resolution = rate / count
    global_peak = float(amplitude.max())
    if global_peak < 1e-6:
        return {
            "status": "insufficient_signal",
            "decision": "retain",
            "partials": [],
            "independent_attack_confirmed": False,
        }
    competing = sorted(
        {
            e.pitch
            for e in events
            if e.pitch != event.pitch
            and abs(e.start_sec - event.start_sec) <= 0.08
            and e.end_sec >= start
        }
    )
    partials = []
    for order in range(1, PARTIALS + 1):
        target = _frequency(event.pitch) * order
        lo, hi = _interval(target, resolution)
        if lo <= 0 or hi >= rate / 2:
            continue
        indices = np.flatnonzero((frequencies >= lo) & (frequencies <= hi))
        maxima = indices[
            (amplitude[indices] >= amplitude[indices - 1])
            & (amplitude[indices] >= amplitude[indices + 1])
        ]
        peak_index = int(maxima[np.argmax(amplitude[maxima])]) if len(maxima) else None
        peak_hz = float(frequencies[peak_index]) if peak_index is not None else None
        peak_amp = float(amplitude[peak_index]) if peak_index is not None else None
        # This amplitude floor is not an SNR estimate or a guarantee against sidelobes.
        observed = bool(peak_amp is not None and peak_amp >= max(1e-6, global_peak * 0.01))
        overlaps = []
        for pitch in competing:
            fundamental = _frequency(pitch)
            tuning_ratio = 2 ** (TUNING_CENTS / 1200)
            maximum_order = int((hi + 2 * resolution) * tuning_ratio / fundamental)
            for harmonic in range(1, maximum_order + 1):
                other = fundamental * harmonic
                parent_lo, parent_hi = _interval(other, resolution)
                if parent_lo <= hi and parent_hi >= lo:
                    overlaps.append(
                        {"model_pitch": pitch, "harmonic_order": harmonic, "nominal_hz": other}
                    )
        partials.append(
            {
                "order": order,
                "nominal_hz": target,
                "peak_hz": peak_hz,
                "peak_amplitude": peak_amp,
                "observed": observed,
                "compatible_modeled_partials": overlaps,
                "attribution": "overlapping_modeled_family"
                if overlaps
                else ("upper_frequency_support" if observed else "not_observed"),
            }
        )
    supports = sum(p["attribution"] == "upper_frequency_support" for p in partials)
    return {
        "status": "upper_frequency_support" if supports >= 2 else "ambiguous",
        "decision": "retain",
        "independent_attack_confirmed": False,
        "event": {"pitch": event.pitch, "start_sec": event.start_sec, "end_sec": event.end_sec},
        "window_start_sec": left / rate,
        "window_end_sec": right / rate,
        "window_samples": count,
        "fft_samples": size,
        "effective_bin_width_hz": resolution,
        "padded_sample_spacing_hz": rate / size,
        "tuning_tolerance_cents": TUNING_CENTS,
        "amplitude_floor": max(1e-6, global_peak * 0.01),
        "peak_criterion": "relative_amplitude_only_not_noise_calibrated",
        "competing_model_pitches": competing,
        "upper_supported_partial_count": supports,
        "partials": partials,
        "limitation": (
            "frequency support is not a separate-key proof; absent peaks do not prove silence"
        ),
    }
