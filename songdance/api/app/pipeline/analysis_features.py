import numpy as np

DEFAULT_KEY_SIGNATURE = "C major"
_MAJOR_PROFILE = np.asarray(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
)
_MINOR_PROFILE = np.asarray(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
)
_PITCH_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


def rank_meter_candidates(
    onset_envelope: np.ndarray,
    beat_frames: np.ndarray,
    accent_envelope: np.ndarray | None = None,
) -> list[dict[str, float | int | str]]:
    if beat_frames.size < 6 or onset_envelope.size == 0:
        return [
            {"value": value, "confidence": 0.0, "phase": 0}
            for value in ("4/4", "3/4", "6/8")
        ]
    frames = np.clip(beat_frames, 0, len(onset_envelope) - 1)
    strengths = _normalized_strengths(onset_envelope, frames)
    if accent_envelope is not None and accent_envelope.size:
        accent_frames = np.clip(beat_frames, 0, len(accent_envelope) - 1)
        strengths = strengths + 2 * _normalized_strengths(
            accent_envelope, accent_frames
        )
    three_score, three_phase = _accent_score(strengths, 3)
    four_score, four_phase = _accent_score(strengths, 4)
    mid_frames = ((beat_frames[:-1] + beat_frames[1:]) / 2).astype(int)
    mid_strength = float(np.mean(onset_envelope[mid_frames])) if mid_frames.size else 0.0
    beat_strength = float(np.mean(strengths)) + 1e-9
    compound_ratio = float(np.clip(mid_strength / beat_strength, 0.0, 1.0))
    raw = {
        "4/4": (four_score, four_phase),
        "3/4": (three_score * (1.0 - compound_ratio), three_phase),
        "6/8": (three_score * compound_ratio, three_phase),
    }
    total = sum(score for score, _phase in raw.values()) + 1e-9
    ranked = [
        {"value": value, "confidence": round(score / total, 6), "phase": phase}
        for value, (score, phase) in raw.items()
    ]
    return sorted(ranked, key=lambda item: (-float(item["confidence"]), str(item["value"])))


def rank_key_candidates(
    chroma: np.ndarray, *, tonic_hint: int | None = None
) -> list[dict[str, float | str | bool]]:
    pitch_energy = np.mean(chroma, axis=1)
    if pitch_energy.size != 12 or float(np.sum(pitch_energy)) <= 1e-9:
        return [{"value": DEFAULT_KEY_SIGNATURE, "confidence": 0.0}]
    candidates = []
    total_energy = float(np.sum(pitch_energy))
    for tonic in range(12):
        for mode, profile in (("major", _MAJOR_PROFILE), ("minor", _MINOR_PROFILE)):
            score = float(np.corrcoef(pitch_energy, np.roll(profile, tonic))[0, 1])
            value = f"{_PITCH_NAMES[tonic]} {mode}"
            leading_tone = (tonic + 11) % 12
            leading_tone_supported = bool(pitch_energy[leading_tone] / total_energy >= 0.08)
            candidates.append((value, score, leading_tone_supported))
    candidates.sort(key=lambda item: (-item[1], item[0]))
    supported = [item for item in candidates if item[2] or _is_zero_accidental_key(item[0])]
    ranked = supported or candidates
    ranked.sort(key=lambda item: (-item[1], item[0]))
    if tonic_hint is not None and ranked and ranked[0][0].endswith(" minor") and not ranked[0][2]:
        relative_major = (tonic_hint - 3) % 12
        relative_value = f"{_PITCH_NAMES[relative_major]} major"
        relative = next((item for item in ranked if item[0] == relative_value), None)
        if relative is not None and relative[2]:
            ranked.remove(relative)
            ranked.insert(0, relative)
    confidence = float(
        np.clip((ranked[0][1] - ranked[1][1]) / 0.25, 0.0, 1.0)
    )
    return [
        {
            "value": value,
            "confidence": round(confidence if index == 0 else 0.0, 6),
            "leading_tone_supported": supported_flag,
        }
        for index, (value, _score, supported_flag) in enumerate(ranked[:3])
    ]


def _is_zero_accidental_key(value: str) -> bool:
    return value in {"C major", "A minor"}


def _accent_score(strengths: np.ndarray, beats_per_measure: int) -> tuple[float, int]:
    phase_scores = []
    for phase in range(beats_per_measure):
        accented = strengths[phase::beats_per_measure]
        others = np.delete(strengths, np.arange(phase, len(strengths), beats_per_measure))
        phase_scores.append(max(0.0, float(np.mean(accented) - np.mean(others))) + 1e-6)
    winning_phase = max(range(beats_per_measure), key=phase_scores.__getitem__)
    return phase_scores[winning_phase], winning_phase


def _normalized_strengths(envelope: np.ndarray, frames: np.ndarray) -> np.ndarray:
    scale = float(np.percentile(envelope, 95)) + 1e-9
    return envelope[frames] / scale
