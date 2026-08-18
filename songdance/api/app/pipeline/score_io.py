from pathlib import Path
from typing import TYPE_CHECKING

from music21 import converter

from app.pipeline.errors import ScoreGenerationError
from app.pipeline.score_validation import (
    raise_for_structure_errors,
    score_structure_summary,
)

if TYPE_CHECKING:
    from app.pipeline.score import ScoredTranscription


def write_quantized_midi(scored: "ScoredTranscription", destination: Path) -> None:
    try:
        scored.score.write("midi", fp=str(destination))
    except Exception as error:
        raise ScoreGenerationError("量化 MIDI 生成失败") from error


def write_musicxml(scored: "ScoredTranscription", destination: Path) -> None:
    try:
        scored.score.write("musicxml", fp=str(destination))
        read_musicxml_structure(destination)
    except Exception as error:
        raise ScoreGenerationError("MusicXML 生成失败") from error


def read_musicxml_structure(source: Path) -> dict[str, object]:
    parsed = converter.parse(str(source))
    raise_for_structure_errors(parsed, validate_measure_durations=True)
    return score_structure_summary(parsed, validate_measure_durations=True)
