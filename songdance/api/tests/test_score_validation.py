import json
from pathlib import Path

import pretty_midi
import pytest
from music21 import expressions, stream

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.score import SCORE_RECONSTRUCTION_FALLBACK, build_score, write_musicxml
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.sustain import extract_sustain_evidence
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


def test_repeated_arpeggio_is_rendered_as_two_single_voice_staves(tmp_path) -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    artifact_root = fixture_root / "structure-review-artifacts/04-arpeggios"
    timeline = json.loads((artifact_root / "timeline.json").read_text(encoding="utf-8"))
    events = [
        NoteEvent(**{key: value for key, value in item.items() if key != "id"})
        for item in timeline["notes"]
    ]
    evidence = extract_sustain_evidence(
        fixture_root / "generated/04-arpeggios.wav",
        pretty_midi.PrettyMIDI(str(fixture_root / "generated/04-arpeggios.mid")),
    )

    scored = build_score(
        events,
        analysis=StructureAnalysis(**timeline["analysis"]),
        sustain_evidence=evidence,
    )
    destination = tmp_path / "arpeggio.musicxml"
    write_musicxml(scored, destination)
    xml = destination.read_text(encoding="utf-8")

    assert xml.count("<part id=") == 2
    assert "<voice>" not in xml
    assert xml.count("<pedal ") == 2
    assert len(list(scored.score.recurse().getElementsByClass(stream.Voice))) == 0
    assert len(list(scored.score.recurse().getElementsByClass(expressions.PedalMark))) == 1
    assert scored.reconstruction["voice_compression"]["single_voice_applied"] is True


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

    result = validate_external_parsers([destination])[str(destination.resolve())]

    assert result["xmllint"]["status"] == "passed"
    assert result["osmd"]["status"] == "passed"
    assert result["osmd"]["measure_count"] >= 1
    assert result["osmd"]["svg_count"] >= 1


def test_external_parser_results_keep_duplicate_basenames_separate(tmp_path, monkeypatch) -> None:
    first = tmp_path / "first" / "score.musicxml"
    second = tmp_path / "second" / "score.musicxml"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("<score-partwise/>", encoding="utf-8")
    second.write_text("<score-partwise/>", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.score_parser_validation._validate_xmllint",
        lambda path: {"status": "passed", "source": str(path)},
    )
    monkeypatch.setattr(
        "scripts.score_parser_validation._validate_osmd",
        lambda paths: {str(path): {"status": "passed", "source": str(path)} for path in paths},
    )

    result = validate_external_parsers([first, second])

    assert set(result) == {str(first.resolve()), str(second.resolve())}
    assert result[str(first.resolve())]["osmd"]["source"] == str(first.resolve())
    assert result[str(second.resolve())]["osmd"]["source"] == str(second.resolve())
