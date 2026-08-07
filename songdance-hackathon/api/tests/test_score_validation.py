import json

import pytest

from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.score import SCORE_RECONSTRUCTION_FALLBACK, build_score, write_musicxml
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.transcribe import NoteEvent
from scripts.score_parser_validation import validate_external_parsers


def test_reconstructed_score_has_chords_and_no_voice_overlap() -> None:
    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0, 1, 64, 90, 0.9),
            NoteEvent(0, 1, 67, 90, 0.9),
            NoteEvent(0.5, 1.5, 72, 90, 0.9),
        ]
    )

    assert scored.reconstruction["status"] == "reconstructed"
    assert scored.reconstruction["chord_count"] >= 1
    assert scored.reconstruction["voice_count"] >= 2
    assert score_structure_errors(scored.score) == []


def test_reconstruction_failure_returns_explicit_basic_score_fallback(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(
        "app.pipeline.score._build_reconstructed_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("invalid voices")),
    )

    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0.5, 1.5, 64, 90, 0.9),
        ]
    )
    paths = artifact_paths(tmp_path)
    write_timeline(scored, paths["timeline"])
    timeline = json.loads(paths["timeline"].read_text(encoding="utf-8"))

    assert scored.reconstruction["status"] == "fallback"
    assert scored.reconstruction["error_code"] == "SCORE_RECONSTRUCTION_FAILED"
    assert SCORE_RECONSTRUCTION_FALLBACK in scored.quality_flags
    assert timeline["reconstruction"]["fallback_used"] is True
    assert score_structure_errors(scored.score) == []


def test_reconstruction_programming_error_is_not_hidden_by_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.pipeline.score._build_reconstructed_score",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("broken code")),
    )

    with pytest.raises(RuntimeError, match="broken code"):
        build_score([NoteEvent(0, 1, 60, 90, 0.9)])


def test_musicxml_loads_in_osmd_and_an_independent_xml_parser(tmp_path) -> None:
    destination = tmp_path / "parser-check.musicxml"
    scored = build_score(
        [
            NoteEvent(0, 1, 48, 90, 0.9),
            NoteEvent(0, 1, 60, 90, 0.9),
            NoteEvent(0, 1, 64, 90, 0.9),
        ]
    )
    write_musicxml(scored, destination)

    result = validate_external_parsers([destination])[destination.name]

    assert result["xmllint"]["status"] == "passed"
    assert result["osmd"]["status"] == "passed"
    assert result["osmd"]["measure_count"] >= 1
    assert result["osmd"]["svg_count"] >= 1
