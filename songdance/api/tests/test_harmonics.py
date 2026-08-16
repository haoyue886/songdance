import json
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf

from app.pipeline.cleanup import HARMONIC_CANDIDATE_REMOVED, clean_note_events
from app.pipeline.harmonics import (
    HARMONIC_AUDIO_EVIDENCE,
    HarmonicEvidence,
    HarmonicEvidenceConfig,
    HarmonicRemoval,
    extract_harmonic_evidence,
)
from app.pipeline.quality import evaluate_note_events
from app.pipeline.transcribe import NoteEvent
from app.services.transcription import run_transcription_job
from tests.test_jobs import create_job

SAMPLE_RATE = 22_050


def _write_tones(
    path: Path,
    tones: list[tuple[float, float, float, float]],
    *,
    duration: float = 1.2,
) -> None:
    times = np.arange(round(duration * SAMPLE_RATE)) / SAMPLE_RATE
    audio = np.zeros_like(times)
    fade_samples = round(0.01 * SAMPLE_RATE)
    for frequency, amplitude, start, end in tones:
        mask = (times >= start) & (times < end)
        tone_times = times[mask] - start
        signal = amplitude * np.sin(2 * np.pi * frequency * tone_times)
        envelope = np.ones(signal.size)
        fade = min(fade_samples, signal.size // 2)
        if fade:
            envelope[:fade] = np.linspace(0, 1, fade, endpoint=False)
            envelope[-fade:] = np.linspace(1, 0, fade, endpoint=False)
        audio[mask] += signal * envelope
    sf.write(path, audio, SAMPLE_RATE)


def test_weak_aligned_harmonic_is_removed_with_audio_evidence(tmp_path: Path) -> None:
    audio_path = tmp_path / "harmonic.wav"
    _write_tones(
        audio_path,
        [(220.0, 0.8, 0.1, 1.0), (440.0, 0.08, 0.1, 1.0)],
    )
    fundamental = NoteEvent(0.1, 1.0, 57, 100, 0.9)
    harmonic = NoteEvent(0.1, 1.0, 69, 100, 0.9)

    evidence = extract_harmonic_evidence(audio_path, [fundamental, harmonic])
    result = clean_note_events(
        [fundamental, harmonic], harmonic_evidence=evidence
    )

    assert result.events == [fundamental]
    assert result.reason_counts[HARMONIC_CANDIDATE_REMOVED] == 1
    assert evidence.status == "available"
    assert len(evidence.removals) == 1
    removal = evidence.removals[0]
    assert removal.fundamental_pitch == 57
    assert removal.harmonic_pitch == 69
    assert removal.harmonic_number == 2
    assert removal.energy_ratio <= 0.22
    assert removal.independent_onset is False
    assert removal.reason == HARMONIC_AUDIO_EVIDENCE


def test_independently_started_octave_is_preserved(tmp_path: Path) -> None:
    audio_path = tmp_path / "independent-octave.wav"
    _write_tones(
        audio_path,
        [(220.0, 0.8, 0.1, 1.0), (440.0, 0.08, 0.5, 1.0)],
    )
    fundamental = NoteEvent(0.1, 1.0, 57, 100, 0.9)
    octave = NoteEvent(0.5, 1.0, 69, 20, 0.9)

    evidence = extract_harmonic_evidence(audio_path, [fundamental, octave])
    result = clean_note_events([fundamental, octave], harmonic_evidence=evidence)

    assert evidence.status == "available"
    assert evidence.removals == ()
    assert result.events == [fundamental, octave]
    assert result.reason_counts[HARMONIC_CANDIDATE_REMOVED] == 0


def test_midi_octave_without_audio_evidence_is_never_removed() -> None:
    events = [
        NoteEvent(0.0, 1.0, 57, 100, 0.9),
        NoteEvent(0.0, 1.0, 69, 1, 0.9),
    ]

    result = clean_note_events(events)

    assert result.events == events
    assert result.harmonic_evidence.status == "unavailable"
    assert result.reason_counts[HARMONIC_CANDIDATE_REMOVED] == 0


def test_missing_or_silent_audio_disables_harmonic_removal(tmp_path: Path) -> None:
    events = [
        NoteEvent(0.0, 1.0, 57, 100, 0.9),
        NoteEvent(0.0, 1.0, 69, 1, 0.9),
    ]
    silent_path = tmp_path / "silent.wav"
    sf.write(silent_path, np.zeros(SAMPLE_RATE), SAMPLE_RATE)

    missing = extract_harmonic_evidence(tmp_path / "missing.wav", events)
    silent = extract_harmonic_evidence(silent_path, events)

    assert missing.status == silent.status == "unavailable"
    assert clean_note_events(events, harmonic_evidence=missing).events == events
    assert clean_note_events(events, harmonic_evidence=silent).events == events


def test_service_keeps_raw_artifacts_and_audits_harmonic_removal(
    api_client, monkeypatch
) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    fundamental = NoteEvent(0.1, 1.0, 57, 100, 0.9)
    harmonic = NoteEvent(0.1, 1.0, 69, 20, 0.9)
    raw_midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    for event in (fundamental, harmonic):
        piano.notes.append(
            pretty_midi.Note(
                velocity=event.velocity,
                pitch=event.pitch,
                start=event.start_sec,
                end=event.end_sec,
            )
        )
    raw_midi.instruments.append(piano)
    removal = HarmonicRemoval(
        fundamental_pitch=57,
        harmonic_pitch=69,
        harmonic_start_sec=0.1,
        harmonic_end_sec=1.0,
        harmonic_number=2,
        tuning_error_cents=0.0,
        energy_ratio=0.1,
        independent_onset=False,
    )
    evidence = HarmonicEvidence(
        version=HarmonicEvidenceConfig().version,
        status="available",
        source="AUDIO_STFT",
        removals=(removal,),
    )
    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
        lambda *_args, **_kwargs: ([fundamental, harmonic], raw_midi),
    )
    monkeypatch.setattr(
        "app.services.transcription.extract_harmonic_evidence",
        lambda *_args, **_kwargs: evidence,
    )

    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )

    artifact_root = storage_path / f"jobs/{job_id}/artifacts/attempt-1"
    stored_raw_midi = pretty_midi.PrettyMIDI(str(artifact_root / "raw.mid"))
    raw_timeline = json.loads((artifact_root / "raw-timeline.json").read_text())
    timeline = json.loads((artifact_root / "timeline.json").read_text())
    report = json.loads(client.get(f"/jobs/{job_id}").json()["quality_report"]["summary"])
    assert sum(len(item.notes) for item in stored_raw_midi.instruments) == 2
    assert len(raw_timeline["notes"]) == 2
    assert len(timeline["notes"]) == 1
    assert report["raw_note_count"] == 2
    assert report["cleaned_note_count"] == 1
    assert report["cleanup"]["reason_counts"][HARMONIC_CANDIDATE_REMOVED] == 1
    assert report["cleanup"]["harmonic_evidence"]["removals"] == [removal.summary()]


def test_arpeggio_fixture_removes_harmonics_without_recall_loss() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    raw_midi_path = fixture_root / "structure-review-artifacts/04-arpeggios/raw.mid"
    reference_midi_path = fixture_root / "generated/04-arpeggios.mid"
    raw_midi_bytes = raw_midi_path.read_bytes()

    def read_events(path: Path) -> list[NoteEvent]:
        midi = pretty_midi.PrettyMIDI(str(path))
        return [
            NoteEvent(note.start, note.end, note.pitch, note.velocity, 1.0)
            for instrument in midi.instruments
            for note in instrument.notes
        ]

    raw_events = read_events(raw_midi_path)
    reference_events = read_events(reference_midi_path)
    evidence = extract_harmonic_evidence(
        fixture_root / "generated/04-arpeggios.wav", raw_events
    )
    cleaned = clean_note_events(raw_events, harmonic_evidence=evidence)

    raw_metrics = evaluate_note_events(raw_events, reference_events)
    cleaned_metrics = evaluate_note_events(cleaned.events, reference_events)
    recall_delta = float(cleaned_metrics["recall"]) - float(raw_metrics["recall"])
    assert evidence.status == "available"
    assert len(evidence.removals) > 0
    assert recall_delta >= -0.05
    assert raw_midi_path.read_bytes() == raw_midi_bytes
    json.dumps(evidence.summary())
