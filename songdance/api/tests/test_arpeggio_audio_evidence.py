from pathlib import Path

import numpy as np
import soundfile as sf

from app.pipeline.arpeggio_audio_evidence import (
    EvidenceTimeMap,
    is_confirmed_same_pitch_decay,
)
from app.pipeline.arpeggio_resonance import filter_simple_arpeggio_resonance
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import (
    HarmonicEvidence,
    HarmonicEvidenceConfig,
    HarmonicRemoval,
    NoteOnsetEvidence,
    extract_harmonic_evidence,
)
from app.pipeline.transcribe import NoteEvent

SAMPLE_RATE = 22_050
PATTERN = (48, 55, 60, 64, 67, 72, 67, 64)


def _same_pitch_evidence(
    candidate: NoteEvent,
    *,
    onset_growth: float = 1.0,
) -> HarmonicEvidence:
    return HarmonicEvidence(
        version=HarmonicEvidenceConfig().version,
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=(
            NoteOnsetEvidence(
                pitch=candidate.pitch,
                start_sec=candidate.start_sec,
                end_sec=candidate.end_sec,
                onset_growth=onset_growth,
                independent_onset=False,
                pre_onset_energy=2.0,
                onset_energy=2.0 * onset_growth,
            ),
        ),
    )


def test_same_pitch_decay_requires_velocity_and_duration_coherence() -> None:
    previous = NoteEvent(0.0, 0.4, 60, 90, 0.9)
    confirmed = NoteEvent(0.25, 0.45, 60, 55, 0.4)
    strong = NoteEvent(0.25, 0.45, 60, 80, 0.4)
    long = NoteEvent(0.25, 1.1, 60, 55, 0.4)
    time_map = EvidenceTimeMap(0.0, 0.25, 0.0, 0.25)

    measurement = is_confirmed_same_pitch_decay(
        confirmed,
        {60: previous},
        _same_pitch_evidence(confirmed),
        time_map,
    )

    assert measurement is not None
    assert abs(measurement.overlap_seconds - 0.15) < 1e-9
    assert measurement.energy_ratio == 1.0
    assert measurement.velocity_ratio == 55 / 90
    assert abs(measurement.duration_ratio - 0.5) < 1e-9
    assert (
        is_confirmed_same_pitch_decay(
            strong,
            {60: previous},
            _same_pitch_evidence(strong),
            time_map,
        )
        is None
    )
    assert (
        is_confirmed_same_pitch_decay(
            long,
            {60: previous},
            _same_pitch_evidence(long),
            time_map,
        )
        is None
    )


def _write_repeated_octaves(
    path: Path,
    events: list[NoteEvent],
    *,
    background_pitch: int | None = None,
    background_amplitude: float = 0.0,
) -> None:
    times = np.arange(round(6.0 * SAMPLE_RATE)) / SAMPLE_RATE
    audio = np.zeros_like(times)
    for event in events:
        mask = (times >= event.start_sec) & (times < event.end_sec)
        local = times[mask] - event.start_sec
        duration = event.end_sec - event.start_sec
        envelope = np.minimum(1.0, local / 0.01) * np.minimum(
            1.0,
            np.maximum(0.0, (duration - local) / 0.03),
        )
        amplitude = 0.1 if event.velocity == 40 else 0.35
        frequency = 440.0 * 2 ** ((event.pitch - 69) / 12)
        audio[mask] += amplitude * np.sin(2 * np.pi * frequency * local) * envelope
    if background_pitch is not None and background_amplitude > 0:
        frequency = 440.0 * 2 ** ((background_pitch - 69) / 12)
        audio += background_amplitude * np.sin(2 * np.pi * frequency * times)
    audio *= 0.8 / np.max(np.abs(audio))
    sf.write(path, (audio * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")


def _write_repeated_third_partials(
    path: Path,
    events: list[NoteEvent],
    false_partials: list[NoteEvent],
) -> None:
    times = np.arange(round(6.0 * SAMPLE_RATE)) / SAMPLE_RATE
    audio = np.zeros_like(times)
    for event in events:
        if event in false_partials:
            continue
        mask = (times >= event.start_sec) & (times < event.end_sec)
        local = times[mask] - event.start_sec
        duration = event.end_sec - event.start_sec
        envelope = np.minimum(1.0, local / 0.01) * np.minimum(
            1.0,
            np.maximum(0.0, (duration - local) / 0.03),
        )
        frequency = 440.0 * 2 ** ((event.pitch - 69) / 12)
        audio[mask] += 0.35 * np.sin(2 * np.pi * frequency * local) * envelope
        if event.pitch == 60:
            audio[mask] += 0.1 * np.sin(2 * np.pi * frequency * 3 * local) * envelope
    audio *= 0.8 / np.max(np.abs(audio))
    sf.write(path, (audio * 32767).astype(np.int16), SAMPLE_RATE, subtype="PCM_16")


def _events_with_true_octaves(
    *, octave_duration: float = 0.2
) -> tuple[list[NoteEvent], list[NoteEvent]]:
    events = []
    octaves = []
    for index, pitch in enumerate(PATTERN * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.2, pitch, 90, 0.9))
        if pitch == 60:
            octave = NoteEvent(start, start + octave_duration, 72, 40, 0.8)
            events.append(octave)
            octaves.append(octave)
    return events, octaves


def _events_with_true_third_harmonic_interval() -> tuple[list[NoteEvent], list[NoteEvent]]:
    events = []
    upper_notes = []
    for index, pitch in enumerate(PATTERN * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.2, pitch, 90, 0.9))
        if pitch == 60:
            upper = NoteEvent(start, start + 0.1, 79, 40, 0.8)
            events.append(upper)
            upper_notes.append(upper)
    return events, upper_notes


def test_production_audio_evidence_preserves_weak_simultaneous_octaves(
    tmp_path: Path,
) -> None:
    events, octaves = _events_with_true_octaves()
    audio_path = tmp_path / "played-octaves.wav"
    _write_repeated_octaves(audio_path, events)
    evidence = extract_harmonic_evidence(audio_path, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)

    result = filter_simple_arpeggio_resonance(
        cleaned.events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    assert all(octave in result.events for octave in octaves)
    assert all(octave in cleaned.events for octave in octaves)
    assert result.removed_event_count == 0


def test_production_audio_evidence_preserves_short_independent_octaves(
    tmp_path: Path,
) -> None:
    events, octaves = _events_with_true_octaves(octave_duration=0.1)
    audio_path = tmp_path / "played-short-octaves.wav"
    _write_repeated_octaves(audio_path, events)
    evidence = extract_harmonic_evidence(audio_path, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)

    result = filter_simple_arpeggio_resonance(
        cleaned.events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    matching_observations = [
        item
        for item in evidence.observations
        if item.fundamental_pitch == 60 and item.harmonic_pitch == 72
    ]
    assert all(
        item.tracking_energy_ratio is not None and item.tracking_energy_ratio < 0.3
        for item in matching_observations
    )
    assert all(octave in result.events for octave in octaves)
    assert all(octave in cleaned.events for octave in octaves)
    assert result.removed_event_count == 0


def test_production_audio_evidence_preserves_short_independent_twelfths(
    tmp_path: Path,
) -> None:
    events, upper_notes = _events_with_true_third_harmonic_interval()
    audio_path = tmp_path / "played-short-twelfths.wav"
    _write_repeated_octaves(audio_path, events)
    evidence = extract_harmonic_evidence(audio_path, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)

    result = filter_simple_arpeggio_resonance(
        cleaned.events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    matching_observations = [
        item
        for item in evidence.observations
        if item.fundamental_pitch == 60 and item.harmonic_pitch == 79
    ]
    assert len(matching_observations) == len(upper_notes)
    assert all(
        item.release_energy_ratio is not None and item.release_energy_ratio <= 0.25
        for item in matching_observations
    )
    assert all(upper in result.events for upper in upper_notes)
    assert all(upper in cleaned.events for upper in upper_notes)
    assert result.removed_event_count == 0


def test_release_probe_subtracts_stationary_frequency_noise(tmp_path: Path) -> None:
    events, upper_notes = _events_with_true_third_harmonic_interval()
    audio_path = tmp_path / "played-short-twelfths-with-noise.wav"
    _write_repeated_octaves(
        audio_path,
        events,
        background_pitch=79,
        background_amplitude=0.08,
    )
    evidence = extract_harmonic_evidence(audio_path, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)
    result = filter_simple_arpeggio_resonance(
        cleaned.events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    assert all(upper in cleaned.events for upper in upper_notes)
    assert all(upper in result.events for upper in upper_notes)


def test_release_probe_fails_closed_when_next_same_pitch_occupies_window(
    tmp_path: Path,
) -> None:
    events, upper_notes = _events_with_true_third_harmonic_interval()
    following_notes = [
        NoteEvent(upper.end_sec + 0.035, upper.end_sec + 0.085, 79, 80, 0.9)
        for upper in upper_notes
    ]
    events += following_notes
    audio_path = tmp_path / "played-short-twelfths-with-following-notes.wav"
    _write_repeated_octaves(audio_path, events)
    evidence = extract_harmonic_evidence(audio_path, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)

    matching_observations = [
        item
        for item in evidence.observations
        if item.fundamental_pitch == 60
        and item.harmonic_pitch == 79
        and item.harmonic_start_sec in {upper.start_sec for upper in upper_notes}
    ]
    assert len(matching_observations) == len(upper_notes)
    assert all(item.release_energy_ratio is None for item in matching_observations)
    assert all(upper in cleaned.events for upper in upper_notes)
    result = filter_simple_arpeggio_resonance(
        cleaned.events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )
    assert all(upper in result.events for upper in upper_notes)
    assert all(note in result.events for note in following_notes)
    assert result.removed_event_count == 0


def test_production_audio_evidence_removes_natural_third_partials(
    tmp_path: Path,
) -> None:
    events = []
    false_partials = []
    for index, pitch in enumerate(PATTERN * 3):
        start = index * 0.25
        events.append(NoteEvent(start, start + 0.2, pitch, 90, 0.9))
        if pitch == 60:
            partial = NoteEvent(start, start + 0.1, 79, 40, 0.8)
            events.append(partial)
            false_partials.append(partial)
    audio_path = tmp_path / "natural-third-partials.wav"
    _write_repeated_third_partials(audio_path, events, false_partials)
    evidence = extract_harmonic_evidence(audio_path, events)

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    matching_observations = [
        item
        for item in evidence.observations
        if item.fundamental_pitch == 60 and item.harmonic_pitch == 79
    ]
    assert len(matching_observations) == len(false_partials)
    assert all(
        item.release_energy_ratio is not None and item.release_energy_ratio > 0.25
        for item in matching_observations
    )
    assert all(
        item.tracking_energy_ratio is not None and item.tracking_energy_ratio >= 0.3
        for item in matching_observations
    )
    assert all(partial not in result.events for partial in false_partials)
    assert result.removed_event_count == len(false_partials)
    assert len(result.removals) == result.removed_event_count
    assert len(result.summary()["removals"]) == result.removed_event_count
    assert all(item.evidence_type == "harmonic_pair" for item in result.removals)
    assert all(item.harmonic_order == 3 for item in result.removals)
    assert all(item.energy_ratio is not None for item in result.removals)
    assert all(item.release_energy_ratio is not None for item in result.removals)
    assert all(item.decision_reason == "CONFIRMED_HARMONIC_PAIR" for item in result.removals)


def test_harmonic_pair_evidence_only_authorizes_its_own_cycle() -> None:
    events, octaves = _events_with_true_octaves()
    fundamentals = [event for event in events if event.pitch == 60]
    shortened_octaves = [
        NoteEvent(item.start_sec, item.start_sec + 0.1, 79, item.velocity, item.confidence)
        for item in octaves
    ]
    events = [event for event in events if event not in octaves] + shortened_octaves
    evidence = HarmonicEvidence(
        version=HarmonicEvidenceConfig().version,
        status="available",
        source="AUDIO_STFT",
        removals=(),
        observations=(
            HarmonicRemoval(
                fundamental_pitch=60,
                harmonic_pitch=79,
                harmonic_start_sec=shortened_octaves[0].start_sec,
                harmonic_end_sec=shortened_octaves[0].end_sec,
                harmonic_number=3,
                tuning_error_cents=-1.955001,
                energy_ratio=0.05,
                independent_onset=False,
                fundamental_start_sec=fundamentals[0].start_sec,
                fundamental_end_sec=fundamentals[0].end_sec,
                fundamental_velocity=90,
                harmonic_velocity=40,
                onset_delta_seconds=0.0,
                velocity_ratio=40 / 90,
                duration_ratio=0.5,
                release_energy_ratio=0.5,
            ),
        ),
        onset_observations=tuple(
            NoteOnsetEvidence(
                pitch=event.pitch,
                start_sec=event.start_sec,
                end_sec=event.end_sec,
                onset_growth=1.0,
                independent_onset=any(event is item for item in shortened_octaves[1:]),
            )
            for event in events
        ),
    )
    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    assert shortened_octaves[0] not in result.events
    assert all(octave in result.events for octave in shortened_octaves[1:])
    assert result.removed_event_count == 1


def test_unmeasurable_release_does_not_authorize_harmonic_pair_removal() -> None:
    events, octaves = _events_with_true_octaves()
    fundamentals = [event for event in events if event.pitch == 60]
    candidate = NoteEvent(octaves[0].start_sec, octaves[0].start_sec + 0.1, 79, 40, 0.8)
    events = [event for event in events if event is not octaves[0]] + [candidate]
    evidence = HarmonicEvidence(
        version=HarmonicEvidenceConfig().version,
        status="available",
        source="AUDIO_STFT",
        removals=(),
        observations=(
            HarmonicRemoval(
                fundamental_pitch=60,
                harmonic_pitch=79,
                harmonic_start_sec=candidate.start_sec,
                harmonic_end_sec=candidate.end_sec,
                harmonic_number=3,
                tuning_error_cents=-1.955001,
                energy_ratio=0.05,
                independent_onset=False,
                fundamental_start_sec=fundamentals[0].start_sec,
                fundamental_end_sec=fundamentals[0].end_sec,
                fundamental_velocity=90,
                harmonic_velocity=40,
                onset_delta_seconds=0.0,
                velocity_ratio=40 / 90,
                duration_ratio=0.5,
                release_energy_ratio=None,
            ),
        ),
        onset_observations=tuple(
            NoteOnsetEvidence(
                pitch=event.pitch,
                start_sec=event.start_sec,
                end_sec=event.end_sec,
                onset_growth=1.0,
                independent_onset=False,
            )
            for event in events
        ),
    )

    result = filter_simple_arpeggio_resonance(
        events,
        pedal_intervals=((0.0, 6.0),),
        harmonic_evidence=evidence,
    )

    assert candidate in result.events
    assert not any(
        item.candidate_pitch == candidate.pitch
        and item.candidate_start_sec == candidate.start_sec
        and item.candidate_end_sec == candidate.end_sec
        for item in result.removals
    )
