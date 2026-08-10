import io
from contextlib import redirect_stdout
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pretty_midi
from basic_pitch import FilenameSuffix, build_icassp_2022_model_path
from basic_pitch.inference import Model, predict

from app.pipeline.errors import ModelInferenceError, NoNotesDetectedError

ONSET_THRESHOLD = 0.5
FRAME_THRESHOLD = 0.3


def model_version(
    onset_threshold: float = ONSET_THRESHOLD, frame_threshold: float = FRAME_THRESHOLD
) -> str:
    return (
        "basic-pitch-0.4.0/icassp-2022-onnx/"
        f"o{onset_threshold:g}-f{frame_threshold:g}"
    )


MODEL_VERSION = model_version()


@dataclass(frozen=True)
class NoteEvent:
    start_sec: float
    end_sec: float
    pitch: int
    velocity: int
    confidence: float
    hand: str | None = None
    hand_confidence: float | None = None


@lru_cache(maxsize=1)
def load_model() -> Model:
    return Model(build_icassp_2022_model_path(FilenameSuffix.onnx))


def transcribe_audio(
    audio_path: Path,
    *,
    onset_threshold: float = ONSET_THRESHOLD,
    frame_threshold: float = FRAME_THRESHOLD,
) -> tuple[list[NoteEvent], pretty_midi.PrettyMIDI]:
    try:
        with redirect_stdout(io.StringIO()):
            _model_output, raw_midi, raw_events = predict(
                str(audio_path),
                load_model(),
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
            )
    except Exception as error:
        raise ModelInferenceError() from error

    events = [
        NoteEvent(
            start_sec=float(event[0]),
            end_sec=float(event[1]),
            pitch=int(event[2]),
            velocity=max(1, min(127, round(float(event[3]) * 127))),
            confidence=float(event[3]),
        )
        for event in raw_events
        if len(event) >= 4 and float(event[1]) > float(event[0])
    ]
    if not events:
        raise NoNotesDetectedError()
    return events, raw_midi


def write_raw_midi(midi: pretty_midi.PrettyMIDI, destination: Path) -> None:
    try:
        midi.write(str(destination))
    except Exception as error:
        raise ModelInferenceError("原始模型 MIDI 写入失败") from error
