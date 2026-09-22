from dataclasses import replace

import numpy as np
import pytest
import soundfile as sf

from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.score import build_score
from app.pipeline.transcribe import NoteEvent
from scripts.run_structure_review import _notation_context_for_case


def audio_example(path, pitch, amplitude, phase, attack_decay=2.6, neighbor_offset=0.0):
    rate = 22050
    times = np.arange(rate * 3) / rate
    audio = np.zeros_like(times)
    at = 0.7
    tones = [
        (pitch, 0.8, 0.2, 0),
        (67 if pitch != 67 else 70, 0.2, at + neighbor_offset, 0),
        (79, 0.1, at + neighbor_offset, 0),
    ]
    if amplitude:
        tones.append((pitch, amplitude, at, phase))
    for tone_pitch, volume, start, angle in tones:
        relative = times - start
        active = (relative >= 0) & (relative < 1.6)
        x = relative[active]
        decay = attack_decay if tone_pitch == pitch and start == at else 2.6
        envelope = np.minimum(x / 0.008, 1) * np.exp(-decay * x)
        audio[active] += (
            volume * envelope * np.sin(2 * np.pi * 440 * 2 ** ((tone_pitch - 69) / 12) * x + angle)
        )
    sf.write(path, audio, rate, subtype="FLOAT")
    events = [
        NoteEvent(0.2, at, pitch, 90, 0.9),
        NoteEvent(at, 1.2, pitch, 25, 0.25),
        NoteEvent(at + neighbor_offset, 1.2, tones[1][0], 70, 0.8),
        NoteEvent(at + neighbor_offset, 1.2, 79, 70, 0.8),
    ]
    h = extract_harmonic_evidence(
        path, events, include_decay_evidence=True, include_transient_evidence=True
    )
    assert h.status == "available"
    return events, h


@pytest.mark.parametrize("pitch", [48, 64, 72])
def test_actual_audio_uninterrupted_tail_is_removed_amid_dual_attack(tmp_path, pitch):
    events, h = audio_example(tmp_path / "decay.wav", pitch, 0, 0)
    kept, audit = clean_crossing_tails(events, h, 1.0)
    assert events[0] in kept
    assert events[1] not in kept
    assert audit["removed_count"] == 1
    assert audit["removals"][0]["onset_evidence"]["decay_fit_error"] <= 0.05


@pytest.mark.parametrize("pitch", [48, 64, 72])
@pytest.mark.parametrize("amplitude", [0.03, 0.08])
@pytest.mark.parametrize("phase", [0.0, np.pi / 2])
def test_actual_audio_weak_restrike_changes_amplitude_or_phase_and_is_preserved(
    tmp_path, pitch, amplitude, phase
):
    events, h = audio_example(tmp_path / "restrike.wav", pitch, amplitude, phase)
    kept, audit = clean_crossing_tails(events, h, 1.0)
    assert kept == events
    assert audit["removals"] == []


@pytest.mark.parametrize("amplitude", [0.03, 0.08, 0.16])
@pytest.mark.parametrize("offset", [-0.08, -0.04, 0, 0.04, 0.08])
@pytest.mark.parametrize("neighbor_offset", [-0.07, -0.04, 0, 0.04, 0.07])
def test_fast_real_restrike_survives_full_pipeline_even_if_late_decay_looks_clean(
    tmp_path, amplitude, offset, neighbor_offset
):
    from app.pipeline.cleanup import clean_note_events

    path = tmp_path / "short-restrike.wav"
    frequency = 440 * 2 ** ((64 - 69) / 12)
    events, _ = audio_example(path, 64, amplitude, 2 * np.pi * frequency * 0.5, 50, neighbor_offset)
    events[0] = replace(events[0], end_sec=0.7 + offset)
    events[1] = replace(events[1], start_sec=0.7 + offset)
    evidence = extract_harmonic_evidence(
        path, events, include_decay_evidence=True, include_transient_evidence=True
    )
    observation = next(
        o for o in evidence.onset_observations if o.pitch == 64 and o.start_sec > 0.3
    )
    if offset == 0 and neighbor_offset == 0:
        assert observation.decay_fit_error < 0.05
        assert observation.transient_fit_error > 0.01
    cleaned = clean_note_events(
        events, harmonic_evidence=evidence, preserve_simultaneous_unisons=True
    )
    assert len(cleaned.events) == 4
    scored = build_score(
        cleaned.events,
        harmonic_evidence=evidence,
        notation_context=_notation_context_for_case({"texture_hint": "crossing_eighth_melody"}),
    )
    assert scored.reconstruction["crossing_tail_cleanup"]["removed_count"] == 0
    assert sum(e.pitch == 64 for e in scored.notation_notes) == 2


def test_missing_transient_extraction_is_conservative_and_not_implicitly_enabled(tmp_path):
    path = tmp_path / "short.wav"
    events, _ = audio_example(path, 64, 0, 0)
    evidence = extract_harmonic_evidence(path, events, include_decay_evidence=True)
    assert all(o.transient_fit_error is None for o in evidence.onset_observations)
    assert clean_crossing_tails(events, evidence, 1.0)[0] == events


def test_transient_unresolvable_harmonic_overlap_and_audio_edges_are_not_proof(tmp_path):
    from app.pipeline.crossing_attack_evidence import transient_fit_error

    path = tmp_path / "overlap.wav"
    events, _ = audio_example(path, 64, 0, 0)
    audio, rate = sf.read(path)
    # E3's second partial and E4 cannot be separated by this probe.
    collision = [*events, NoteEvent(0.7, 1.2, 52, 80, 0.8)]
    assert transient_fit_error(audio, rate, events[1], collision) is None
    assert transient_fit_error(audio, rate, replace(events[1], start_sec=0.1), events) is None
    assert transient_fit_error(audio, rate, replace(events[1], start_sec=2.9), events) is None


@pytest.mark.parametrize("offset", [-0.04, 0.04, 0.07])
def test_actual_short_restrike_is_preserved_with_staggered_other_hand(tmp_path, offset):
    frequency = 440 * 2 ** ((64 - 69) / 12)
    events, evidence = audio_example(
        tmp_path / "staggered.wav", 64, 0.16, 2 * np.pi * frequency * 0.5, 50, offset
    )
    kept, report = clean_crossing_tails(events, evidence, 1.0)
    assert kept == events
    assert report["removed_count"] == 0
