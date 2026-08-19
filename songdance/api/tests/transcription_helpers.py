from pathlib import Path

import pretty_midi

from app.pipeline.transcribe import NoteEvent
from app.services.transcription import run_transcription_job


def run_service(client, job_id: str) -> None:
    run_transcription_job(
        job_id,
        client.app.state.settings,
        client.app.state.session_factory,
        client.app.state.storage,
    )


def fake_transcription(_audio_path: Path, **_kwargs):
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    piano.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0, end=1))
    midi.instruments.append(piano)
    return [NoteEvent(0, 1, 60, 100, 0.9)], midi
