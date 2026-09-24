"""Explain local evidence limits; never select or delete notes."""

from math import isfinite

from app.pipeline.crossing_tail_cleanup import MAX_DECAY_ERROR, MAX_TRANSIENT_ERROR
from app.pipeline.harmonics import HarmonicEvidenceConfig


def evidence_limits(event, observations):
    config = HarmonicEvidenceConfig()
    # This describes the requested pre-onset probe, not full STFT support.
    result = {
        "pre_onset_probe_clamped": bool(event["start_sec"] < config.onset_window_seconds),
        "local_decay_checks_failed": [],
        "scope": "local necessary checks only; not the full tail deletion decision",
    }
    if len(observations) != 1:
        result["local_decay_checks_failed"].append("missing_or_ambiguous_observation")
        return result
    observation = observations[0]
    failures = result["local_decay_checks_failed"]
    if observation["independent_onset"]:
        failures.append("independent_onset_reported")
    for field in ("onset_growth", "pre_onset_energy", "onset_energy"):
        value = observation[field]
        if value is None or not isfinite(value) or value <= 0:
            failures.append(f"{field}_unavailable_or_invalid")
    for field, maximum in (
        ("decay_fit_error", MAX_DECAY_ERROR),
        ("transient_fit_error", MAX_TRANSIENT_ERROR),
    ):
        value = observation[field]
        if value is None or not isfinite(value) or value < 0:
            failures.append(f"{field}_unavailable_or_invalid")
        elif value > maximum:
            failures.append(f"{field}_above_limit")
    growth = observation["onset_growth"]
    if growth is not None and isfinite(growth) and growth > 1:
        failures.append("onset_growth_above_one")
    before, after = observation["pre_onset_energy"], observation["onset_energy"]
    if before is not None and after is not None and isfinite(before) and isfinite(after):
        if after > before:
            failures.append("energy_increased")
    return result
