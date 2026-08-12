import json

import pytest
from music21 import converter, stream

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


def test_pickup_measure_is_not_rendered_as_a_full_leading_rest(tmp_path) -> None:
    from dataclasses import replace

    from app.pipeline.analysis import AnalysisConfig, fallback_analysis

    analysis = replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        bpm=120,
        beat_grid_seconds=(0.0, 0.5, 1.0, 1.5, 2.0),
        downbeat_grid_seconds=(0.5, 2.5),
        time_signature="4/4",
        time_signature_source="fixture",
    )
    scored = build_score(
        [NoteEvent(0.0, 0.5, 60, 90, 0.9), NoteEvent(0.5, 1.0, 64, 90, 0.9)],
        analysis=analysis,
    )
    destination = tmp_path / "pickup.musicxml"
    write_musicxml(scored, destination)

    parsed = converter.parse(str(destination))
    first_measure = list(parsed.parts[0].getElementsByClass(stream.Measure))[0]
    assert first_measure.paddingLeft == 3
    assert first_measure.duration.quarterLength == 1
    assert score_structure_errors(parsed, validate_measure_durations=True) == []


def test_pickup_measure_uses_one_shared_boundary_for_both_hands() -> None:
    from dataclasses import replace

    from app.pipeline.analysis import AnalysisConfig, fallback_analysis

    analysis = replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        bpm=120,
        beat_grid_seconds=(0.0, 0.5, 1.0, 1.5),
        downbeat_grid_seconds=(0.5, 2.5),
        time_signature="4/4",
        time_signature_source="fixture",
    )
    scored = build_score(
        [NoteEvent(0.0, 0.5, 48, 90, 0.9), NoteEvent(0.25, 0.5, 72, 90, 0.9)],
        analysis=analysis,
    )

    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]
    assert [measure.paddingLeft for measure in first_measures] == [3, 3]
    assert [measure.duration.quarterLength for measure in first_measures] == [1, 1]
    right_rests = list(first_measures[0].recurse().getElementsByClass("Rest"))
    assert [rest.quarterLength for rest in right_rests] == [0.5]
    assert score_structure_errors(scored.score, validate_measure_durations=True) == []


def test_pickup_trims_a_full_leading_rest_when_the_other_hand_is_empty() -> None:
    from dataclasses import replace

    from app.pipeline.analysis import AnalysisConfig, fallback_analysis

    analysis = replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        bpm=120,
        beat_grid_seconds=(0.0, 0.5, 1.0, 1.5),
        downbeat_grid_seconds=(0.5, 2.5),
        time_signature="4/4",
        time_signature_source="fixture",
    )
    scored = build_score([NoteEvent(0.0, 0.5, 72, 90, 0.9)], analysis=analysis)

    first_measures = [
        list(part.getElementsByClass(stream.Measure))[0] for part in scored.score.parts
    ]
    assert [measure.paddingLeft for measure in first_measures] == [3, 3]
    assert [measure.duration.quarterLength for measure in first_measures] == [1, 1]
    assert score_structure_errors(scored.score, validate_measure_durations=True) == []


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


def test_external_parser_results_keep_duplicate_basenames_separate(
    tmp_path, monkeypatch
) -> None:
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
        lambda paths: {
            str(path): {"status": "passed", "source": str(path)} for path in paths
        },
    )

    result = validate_external_parsers([first, second])

    assert set(result) == {str(first.resolve()), str(second.resolve())}
    assert result[str(first.resolve())]["osmd"]["source"] == str(first.resolve())
    assert result[str(second.resolve())]["osmd"]["source"] == str(second.resolve())
