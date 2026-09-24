"""Research-only multi-partial continuity probe; never imported by production."""

import numpy as np

from app.pipeline.crossing_attack_evidence import CENTERS, _estimator

MAX_ERROR = 0.01
MIN_TRACKS = 2
PARTIALS = (1, 2, 3, 4)


def measure(audio, rate, event, events):
    start = event.start_sec
    if start < 0.35 or start + 0.2 >= len(audio) / rate:
        return {"status": "boundary", "tracks": [], "continuous_hypothesis": False}
    neighbors = {
        e.pitch
        for e in events
        if e.pitch != event.pitch and e.start_sec < start + 0.12 and e.end_sec > start - 0.25
    }
    own = [440 * 2 ** ((event.pitch - 69) / 12) * h for h in range(1, 7)]
    other = sorted({440 * 2 ** ((p - 69) / 12) * h for p in neighbors for h in range(1, 7)})
    tracks = []
    for h in PARTIALS:
        target = own[h - 1]
        if target >= rate / 2 - 25:
            tracks.append({"partial": h, "status": "nyquist"})
            continue
        if any(abs(f - target) < 15 for f in other):
            tracks.append({"partial": h, "status": "frequency_collision"})
            continue
        carriers = [target]
        for f in sorted(own + other):
            if f < rate / 2 - 25 and min(abs(f - c) for c in carriers) > 10:
                carriers.append(f)
        estimator = _estimator(tuple(carriers), rate)
        if estimator is None:
            tracks.append({"partial": h, "status": "ill_conditioned"})
            continue
        count = estimator.shape[1]
        values = []
        for center in CENTERS:
            left = round((start + center) * rate) - count // 2
            cosine, sine = estimator @ audio[left : left + count]
            values.append(
                (cosine - 1j * sine) * np.exp(-2j * np.pi * target * (left + count / 2) / rate)
            )
        values, times = np.asarray(values), np.asarray(CENTERS)
        before, after = times < -0.08, times >= -0.04
        if np.median(np.abs(values[before])) < 1e-5:
            tracks.append({"partial": h, "status": "low_energy"})
            continue
        logs = np.log(np.maximum(np.abs(values), 1e-10))
        slope, intercept = np.polyfit(times[before], logs[before], 1)
        if slope >= 0:
            tracks.append({"partial": h, "status": "nondecaying"})
            continue
        phases = np.unwrap(np.angle(values))
        phase_slope, phase_intercept = np.polyfit(times[before], phases[before], 1)
        amplitude_error = np.max(np.abs(logs[after] - (slope * times[after] + intercept)))
        phase_error = np.max(
            np.abs(
                np.angle(
                    np.exp(1j * (phases[after] - (phase_slope * times[after] + phase_intercept)))
                )
            )
        )
        tracks.append(
            {"partial": h, "status": "measured", "error": float(max(amplitude_error, phase_error))}
        )
    measured = [t for t in tracks if t["status"] == "measured"]
    # Missing/colliding tracks do not prove continuity; require redundant available evidence.
    continuous = supports_continuity(tracks)
    return {
        "status": "measured" if measured else "unavailable",
        "tracks": tracks,
        "continuous_hypothesis": bool(continuous),
    }


def supports_continuity(tracks):
    measured = [t for t in tracks if t["status"] == "measured"]
    return bool(
        not any(t["status"] == "nondecaying" for t in tracks)
        and len(measured) >= MIN_TRACKS
        and all(np.isfinite(t["error"]) and 0 <= t["error"] <= MAX_ERROR for t in measured)
    )
