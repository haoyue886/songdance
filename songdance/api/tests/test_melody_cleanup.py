from dataclasses import replace
from pathlib import Path

import pytest

from app.pipeline.harmonics import HarmonicEvidence, NoteOnsetEvidence, extract_harmonic_evidence
from app.pipeline.melody_cleanup import clean_melody_tails
from app.pipeline.transcribe import NoteEvent, transcribe_audio


def evidence(events, decay=None):
    return HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=tuple(
            NoteOnsetEvidence(
                e.pitch,
                e.start_sec,
                e.end_sec,
                0.8 if e == decay else 3,
                e != decay,
                pre_onset_energy=10,
                onset_energy=8 if e == decay else 30,
                decay_fit_error=0.01 if e == decay else None,
            )
            for e in events
        ),
    )


def example():
    return [
        NoteEvent(0, 1.04, 64, 80, 0.9),
        NoteEvent(1, 1.4, 64, 50, 0.5),
        NoteEvent(1, 2, 67, 70, 0.8),
    ]


def test_decaying_duplicate_is_removed_with_audit_and_next_attack_cap():
    events = example()
    before = list(events)
    result = clean_melody_tails(events, evidence(events, events[1]), enabled=True)
    assert events == before
    assert [(e.pitch, e.start_sec, e.end_sec) for e in result.events] == [(64, 0, 1), (67, 1, 2)]
    assert result.removals[0]["event"]["pitch"] == 64
    assert result.removals[0]["onset_evidence"]["independent_onset"] is False
    assert len(result.duration_changes) == 1


@pytest.mark.parametrize(
    "variant",
    [
        "missing",
        "unavailable",
        "retrigger",
        "no_parent",
        "bass",
        "left",
        "ambiguous",
        "nonfinite",
        "contradiction",
    ],
)
def test_uncertainty_and_real_attacks_do_not_delete_notes(variant):
    events = example()
    h = evidence(events, events[1])
    if variant == "missing":
        h = None
    elif variant == "unavailable":
        h = HarmonicEvidence.unavailable()
    elif variant == "retrigger":
        h = evidence(events)
    elif variant == "no_parent":
        events = events[1:]
    elif variant in {"bass", "left"}:
        events.append(NoteEvent(0, 8, 36 if variant == "bass" else 60, 20, 0.2, hand="left"))
    elif variant == "ambiguous":
        h = replace(h, onset_observations=h.onset_observations + (h.onset_observations[1],))
    elif variant == "nonfinite":
        h = replace(
            h,
            onset_observations=tuple(
                replace(o, onset_growth=float("nan")) for o in h.onset_observations
            ),
        )
    elif variant == "contradiction":
        h = replace(
            h, onset_observations=tuple(replace(o, onset_energy=50) for o in h.onset_observations)
        )
    result = clean_melody_tails(events, h, enabled=True)
    assert len(result.events) == len(events)
    assert result.removals == []


def test_weak_real_octave_and_long_independent_voice_are_preserved():
    events = [
        NoteEvent(0, 4, 60, 40, 0.4),
        NoteEvent(0, 1, 72, 20, 0.2),
        NoteEvent(1, 2, 74, 80, 0.8),
        NoteEvent(2, 3, 76, 80, 0.8),
    ]
    result = clean_melody_tails(events, evidence(events), enabled=True)
    assert result.events == events
    assert result.duration_changes == []


@pytest.mark.parametrize("attack_amplitude", [0.03, 0.08, 0.15])
@pytest.mark.parametrize("gap", [0.4, 0.5, 1.0])
@pytest.mark.parametrize("attack_phase", [0, 1.57])
@pytest.mark.parametrize("segmented", [False, True])
def test_audio_weak_restrike_over_decaying_tail_is_not_deleted(
    tmp_path, attack_amplitude, gap, attack_phase, segmented
):
    import numpy as np
    import soundfile as sf

    rate = 22050
    times = np.arange(rate * 3) / rate
    audio = np.zeros_like(times)
    at = 0.2 + gap
    tones = [(64, 0.8, 0.2, at + 0.4), (64, attack_amplitude, at, at + 0.4), (76, 0.2, at, at + 1)]
    for pitch, amplitude, start, end in tones:
        relative = times - start
        active = (relative >= 0) & (times < end)
        phase = relative[active]
        envelope = np.minimum(phase / 0.008, 1) * np.exp(-2.6 * phase)
        audio[active] += (
            amplitude
            * envelope
            * np.sin(
                2 * np.pi * 440 * 2 ** ((pitch - 69) / 12) * phase
                + (attack_phase if start == at else 0)
            )
        )
    path = tmp_path / "weak-restrike.wav"
    sf.write(path, audio, rate)
    events = [
        NoteEvent(0.2, at if segmented else at + 0.4, 64, 90, 0.9),
        NoteEvent(at, at + 0.4, 64, 25, 0.25),
        NoteEvent(at, at + 1, 76, 70, 0.8),
    ]
    actual = extract_harmonic_evidence(path, events, include_decay_evidence=True)
    assert actual.status == "available"
    result = clean_melody_tails(events, actual, enabled=True)
    assert result.removals == []
    assert len(result.events) == 3


def test_no_hint_leaves_default_production_events_untouched():
    events = example()
    assert clean_melody_tails(events, evidence(events, events[1]), enabled=False).events == events


@pytest.mark.parametrize("end,expected", [(1.49, 1), (1.51, 1.51)])
def test_long_sustain_is_not_short_overhang(end, expected):
    events = [NoteEvent(0, end, 64, 80, 0.9), NoteEvent(1, 2, 67, 80, 0.9)]
    result = clean_melody_tails(events, evidence(events), enabled=True)
    assert result.events[0].end_sec == expected


def test_missing_decay_proof_cannot_remove_a_candidate():
    events = example()
    h = evidence(events, events[1])
    h = replace(
        h, onset_observations=tuple(replace(o, decay_fit_error=None) for o in h.onset_observations)
    )
    assert clean_melody_tails(events, h, enabled=True).removals == []


@pytest.fixture(scope="module")
def actual_09(tmp_path_factory):
    from app.pipeline.audio import preprocess_audio

    path = Path(__file__).parent / "fixtures/audio/generated/09-light-noise.wav"
    normalized = tmp_path_factory.mktemp("melody-input") / "normalized.wav"
    preprocess_audio(path, normalized)
    events, midi = transcribe_audio(normalized)
    return (
        path,
        events,
        midi,
        extract_harmonic_evidence(normalized, events, include_decay_evidence=True),
    )


def test_actual_09_audio_evidence_matches_independent_reference(actual_09):
    import pretty_midi

    path, events, midi, h = actual_09
    original = list(events)
    result = clean_melody_tails(events, h, enabled=True)
    truth = pretty_midi.PrettyMIDI(str(path.with_suffix(".mid")))
    expected = sorted([n for i in truth.instruments for n in i.notes], key=lambda n: n.start)
    assert len(events) == 36 and len(result.events) == len(expected) == 30
    assert len(result.removals) == 6
    assert len(midi.instruments[0].notes) == 36
    assert events == original
    for event, reference in zip(result.events, expected, strict=True):
        assert event.pitch == reference.pitch
        assert abs(event.start_sec - reference.start) < 0.1
    for left, right in zip(result.events, result.events[1:], strict=False):
        assert left.end_sec <= right.start_sec
    assert result.events[-1].end_sec == max(original, key=lambda e: e.start_sec).end_sec


def test_actual_09_full_score_uses_evidence_before_quantization(actual_09, tmp_path):
    from music21 import converter, note

    from app.pipeline.analysis import analyze_audio
    from app.pipeline.cleanup import clean_note_events
    from app.pipeline.score import (
        NotationContext,
        build_score,
        read_musicxml_structure,
        write_musicxml,
    )

    path, events, _, h = actual_09
    cleaned = clean_note_events(events, harmonic_evidence=h)
    scored = build_score(
        cleaned.events,
        analysis=analyze_audio(path),
        harmonic_evidence=h,
        notation_context=NotationContext(texture_hint="monophonic_melody"),
    )
    assert scored.reconstruction["fallback_used"] is False
    assert len(scored.reconstruction["melody_cleanup"]["removals"]) == 6
    assert len(scored.notation_notes) == 30
    assert all(e.hand == "right" for e in scored.notation_notes)
    destination = tmp_path / "09.musicxml"
    write_musicxml(scored, destination)
    summary = read_musicxml_structure(destination)
    assert summary["staff_count"] == 1
    assert summary["errors"] == []
    notes = list(converter.parse(destination).recurse().getElementsByClass(note.Note))
    assert len(notes) == 30
    assert all(n.quarterLength == 1 for n in notes[:-1])


def test_hint_does_not_choose_strongest_note_without_audio_evidence():
    from app.pipeline.score import NotationContext, build_score

    scored = build_score(
        example(), notation_context=NotationContext(texture_hint="monophonic_melody")
    )
    assert len(scored.notation_notes) == 3
    assert scored.reconstruction["melody_cleanup"]["removals"] == []
    assert scored.reconstruction["staff_layout"]["value"] == "grand_staff"


def test_actual_device_bass_is_not_removed_by_melody_hint():
    path = Path(__file__).parent / "fixtures/audio/generated/10-device.wav"
    events, _ = transcribe_audio(path)
    h = extract_harmonic_evidence(path, events)
    result = clean_melody_tails(events, h, enabled=True)
    assert result.events == events
    assert result.removals == result.duration_changes == []


def test_missing_evidence_does_not_truncate_regular_treble_sustain():
    from app.pipeline.analysis import AnalysisConfig, fallback_analysis
    from app.pipeline.score import NotationContext, build_score

    events = [NoteEvent(i, i + 1.5, 60 + i % 4, 80, 0.8) for i in range(8)]
    scored = build_score(
        events,
        analysis=replace(fallback_analysis(AnalysisConfig(), "test"), bpm=60),
        notation_context=NotationContext(texture_hint="monophonic_melody"),
    )
    assert all(n.end_sec - n.start_sec == 1.5 for n in scored.notation_notes)
    assert scored.reconstruction["melody_cleanup"]["duration_changes"] == []
