import json
import subprocess
import wave
from dataclasses import replace
from pathlib import Path

import pretty_midi
import pytest
from music21 import chord, converter, meter, note, stream
from rq.timeouts import JobTimeoutException

from app.jobs.tasks import failure_details
from app.pipeline.analysis import AnalysisConfig, fallback_analysis
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.errors import (
    AudioPreprocessError,
    AudioPreprocessTimeoutError,
    ModelInferenceError,
    NoNotesDetectedError,
)
from app.pipeline.score import (
    build_score,
    write_musicxml,
    write_quantized_midi,
)
from app.pipeline.score_validation import score_structure_errors
from app.pipeline.transcribe import (
    FRAME_THRESHOLD,
    MODEL_VERSION,
    ONSET_THRESHOLD,
    NoteEvent,
    load_model,
    model_version,
    transcribe_audio,
    write_raw_midi,
)
from scripts.evaluate_transcription import (
    classify,
    compare_evaluations,
    evaluation_id,
    evaluation_set_id,
)
from tests.conftest import wav_bytes


def test_ffmpeg_preprocesses_to_normalized_mono_wav(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "normalized.wav"
    source.write_bytes(wav_bytes(duration=2, sample_rate=8_000, frequency=440))

    preprocess_audio(source, output)

    with wave.open(str(output), "rb") as audio:
        assert audio.getnchannels() == 1
        assert audio.getframerate() == 22_050
        assert audio.getnframes() / audio.getframerate() == pytest.approx(2, abs=0.02)


def test_ffmpeg_failure_and_timeout_have_preprocess_error_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "invalid.wav"
    invalid.write_bytes(b"not audio")
    with pytest.raises(AudioPreprocessError) as invalid_error:
        preprocess_audio(invalid, tmp_path / "invalid-output.wav")
    assert invalid_error.value.code == "AUDIO_PREPROCESS_FAILED"

    monkeypatch.setattr(
        "app.pipeline.audio.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="ffmpeg", timeout=1)
        ),
    )
    with pytest.raises(AudioPreprocessTimeoutError) as timeout_error:
        preprocess_audio(invalid, tmp_path / "timeout.wav")
    assert timeout_error.value.code == "AUDIO_PREPROCESS_TIMEOUT"


def test_ffmpeg_preprocess_disables_terminal_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.wav"
    destination = tmp_path / "normalized.wav"
    source.write_bytes(b"audio")

    def run(command: list[str], **_kwargs: object) -> None:
        assert command[:2] == ["ffmpeg", "-nostdin"]
        destination.write_bytes(b"0" * 45)

    monkeypatch.setattr("app.pipeline.audio.subprocess.run", run)

    preprocess_audio(source, destination)


def test_basic_pitch_transcribes_a_real_a4_tone(tmp_path: Path) -> None:
    source = tmp_path / "a4.wav"
    normalized = tmp_path / "normalized.wav"
    raw_midi_path = tmp_path / "raw.mid"
    source.write_bytes(wav_bytes(duration=2, sample_rate=22_050, frequency=440))
    preprocess_audio(source, normalized)

    assert load_model().model_type.name == "ONNX"
    events, raw_midi = transcribe_audio(normalized)
    write_raw_midi(raw_midi, raw_midi_path)

    assert any(abs(event.pitch - 69) <= 1 for event in events)
    parsed = pretty_midi.PrettyMIDI(str(raw_midi_path))
    assert sum(len(instrument.notes) for instrument in parsed.instruments) >= 1


def test_basic_pitch_returns_distinct_no_notes_and_model_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    silence = tmp_path / "silence.wav"
    silence.write_bytes(wav_bytes(duration=1.5, sample_rate=22_050))
    with pytest.raises(NoNotesDetectedError) as no_notes:
        transcribe_audio(silence)
    assert no_notes.value.code == "NO_NOTES_DETECTED"

    monkeypatch.setattr(
        "app.pipeline.transcribe.predict",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("model failed")),
    )
    with pytest.raises(ModelInferenceError) as model_error:
        transcribe_audio(silence)
    assert model_error.value.code == "MODEL_INFERENCE_FAILED"


def test_transcription_uses_explicit_threshold_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, float] = {}
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    piano.notes.append(pretty_midi.Note(velocity=100, pitch=60, start=0, end=1))
    midi.instruments.append(piano)

    monkeypatch.setattr("app.pipeline.transcribe.load_model", lambda: object())
    monkeypatch.setattr(
        "app.pipeline.transcribe.predict",
        lambda *_args, **kwargs: (
            captured.update(
                onset_threshold=kwargs["onset_threshold"], frame_threshold=kwargs["frame_threshold"]
            )
            or ({}, midi, [(0, 1, 60, 0.8)])
        ),
    )

    events, _ = transcribe_audio(tmp_path / "input.wav", onset_threshold=0.4, frame_threshold=0.2)

    assert len(events) == 1
    assert captured == {"onset_threshold": 0.4, "frame_threshold": 0.2}
    assert (ONSET_THRESHOLD, FRAME_THRESHOLD) == (0.5, 0.3)
    assert MODEL_VERSION == "basic-pitch-0.4.0/icassp-2022-onnx/o0.5-f0.3"
    assert model_version(0.4, 0.2).endswith("o0.4-f0.2")


def test_fast_polyphonic_bach_fixture_preserves_recall_baseline(tmp_path: Path) -> None:
    source = (
        Path(__file__).parent
        / "fixtures/audio/human-generated/01-bach-capriccio.wav"
    )
    normalized = tmp_path / "normalized.wav"
    raw_midi_path = tmp_path / "raw.mid"

    preprocess_audio(source, normalized)
    events, raw_midi = transcribe_audio(normalized)
    write_raw_midi(raw_midi, raw_midi_path)
    parsed = pretty_midi.PrettyMIDI(str(raw_midi_path))

    assert len(events) >= 275
    assert sum(len(instrument.notes) for instrument in parsed.instruments) >= 275


def test_score_outputs_parseable_midi_musicxml_and_timeline(tmp_path: Path) -> None:
    events = [
        NoteEvent(0, 0.48, 48, 90, 0.9),
        NoteEvent(0, 0.48, 60, 96, 0.92),
        NoteEvent(0.5, 0.98, 64, 100, 0.95),
        NoteEvent(1, 1.48, 67, 104, 0.96),
    ]
    scored = build_score(events, title="Pipeline Test")
    paths = artifact_paths(tmp_path)

    write_quantized_midi(scored, paths["midi"])
    write_musicxml(scored, paths["musicxml"])
    write_timeline(scored, paths["timeline"])

    midi = pretty_midi.PrettyMIDI(str(paths["midi"]))
    assert sum(len(instrument.notes) for instrument in midi.instruments) >= 4
    parsed_score = converter.parse(str(paths["musicxml"]))
    assert len(parsed_score.parts) == 2
    assert len(list(parsed_score.recurse().getElementsByClass("Measure"))) >= 1
    timeline = json.loads(paths["timeline"].read_text(encoding="utf-8"))
    assert timeline["time_signature"] == "4/4"
    assert "TIME_SIGNATURE_ASSUMED_4_4" in timeline["quality_flags"]
    assert "HAND_ASSIGNMENT_INFERRED" in timeline["quality_flags"]
    assert timeline["reconstruction"]["status"] == "reconstructed"
    assert len(timeline["notes"]) == 4
    assert {item["hand"] for item in timeline["notes"]} <= {"left", "right", None}
    assert all(item["hand_confidence"] is not None for item in timeline["notes"])


def test_score_groups_simultaneous_notes_into_chords_and_separates_overlaps() -> None:
    events = [
        NoteEvent(0, 1, 60, 90, 0.9),
        NoteEvent(0, 1, 64, 96, 0.92),
        NoteEvent(0, 1, 67, 100, 0.95),
        NoteEvent(0.5, 1.5, 72, 104, 0.96),
    ]

    scored = build_score(events, title="Chord and voices")

    chords = list(scored.score.recurse().getElementsByClass(chord.Chord))
    voices = list(scored.score.recurse().getElementsByClass(stream.Voice))
    assert any({pitch.midi for pitch in value.pitches} == {60, 64, 67} for value in chords)
    assert len(voices) >= 2
    assert score_structure_errors(scored.score) == []


def test_score_preserves_duration_when_downbeat_requires_measure_offset() -> None:
    analysis = replace(
        fallback_analysis(AnalysisConfig(), "fixture"),
        beat_grid_seconds=(0.0, 0.5, 1.0, 1.5),
        downbeat_grid_seconds=(0.5,),
    )

    scored = build_score([NoteEvent(0, 0.5, 60, 90, 0.9)], analysis=analysis)

    generated = list(scored.score.recurse().getElementsByClass(note.Note))
    assert len(generated) == 1
    assert generated[0].quarterLength == 1


def test_structure_validation_rejects_bad_measures_signatures_and_short_rests() -> None:
    invalid = stream.Score()
    for part_index, signature in enumerate(("4/4", "3/4")):
        part = stream.Part(id=f"part-{part_index}")
        first = stream.Measure(number=1)
        first.insert(0, meter.TimeSignature(signature))
        voice = stream.Voice(id=f"voice-{part_index}")
        voice.insert(0, note.Note(60 + part_index, quarterLength=1))
        voice.insert(1, note.Rest(quarterLength=0.125))
        first.insert(0, voice)
        second = stream.Measure(number=2)
        second.insert(0, note.Note(62 + part_index, quarterLength=1))
        part.append((first, second))
        invalid.insert(0, part)

    errors = score_structure_errors(invalid, validate_measure_durations=True)

    assert "MEASURE_DURATION_MISMATCH" in errors
    assert "INCONSISTENT_TIME_SIGNATURE" in errors
    assert "SUB_GRID_REST_FRAGMENT" in errors


def test_musicxml_uses_expressible_durations_at_inferred_tempo(tmp_path: Path) -> None:
    events = [
        NoteEvent(index * 0.37, index * 0.37 + 0.29, 60 + index % 8, 90, 0.9) for index in range(40)
    ]
    scored = build_score(events, title="Non-integral tempo")
    destination = tmp_path / "score.musicxml"

    write_musicxml(scored, destination)

    parsed = converter.parse(str(destination))
    assert len(list(parsed.recurse().getElementsByClass("Measure"))) >= 1


def test_worker_timeout_has_a_distinct_error_code() -> None:
    timeout = failure_details(JobTimeoutException)
    generic = failure_details(RuntimeError)

    assert timeout[0] == "TRANSCRIPTION_TIMEOUT"
    assert generic[0] == "WORKER_FAILED"


def test_saved_automated_regression_is_current_and_internally_consistent() -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
    result = json.loads((fixture_root / "regression-results.json").read_text(encoding="utf-8"))

    assert manifest["duration_seconds"] == 30
    assert manifest["suite_type"] == "synthetic_structural_regression"
    assert manifest["product_quality_gate"] is False
    assert manifest["authorization"]["third_party_audio"] is False
    assert len(manifest["cases"]) >= 16
    assert len({item["id"] for item in manifest["cases"]}) >= 16
    assert {
        "slow_melody",
        "block_chords",
        "fast_scale",
        "sustain",
        "hand_crossing",
        "waltz_34",
        "compound_68",
        "key_change",
        "noisy_polyphony",
    } <= {item["pattern"] for item in manifest["cases"]}
    assert result["model_version"] == MODEL_VERSION
    assert result["product_quality_gate"] is False
    assert result["total_count"] >= 16
    assert [item["id"] for item in result["results"]] == [item["id"] for item in manifest["cases"]]
    assert all(
        item["rating"] == classify(item["corrections"], item["f1"]) for item in result["results"]
    )
    assert all(item["mean_onset_error_ms"] is not None for item in result["results"])
    assert all(item["mean_pitch_error_semitones"] is not None for item in result["results"])
    assert all(item["musicxml_parse"]["status"] == "passed" for item in result["results"])
    assert all(
        all(parser["status"] == "passed" for parser in item["parser_validation"].values())
        for item in result["results"]
    )
    assert all(item["structure"]["errors"] == [] for item in result["results"])
    assert all(
        item["human_rating"] == {"status": "not_evaluated", "rating": None}
        for item in result["results"]
    )
    assert result["human_evaluation"]["status"] in {"evaluated", "not_evaluated"}
    if result["human_evaluation"]["status"] == "evaluated":
        assert result["human_evaluation"]["total_count"] == 10
    usable = sum(item["rating"] != "needs_redo" for item in result["results"])
    assert result["automated_usable_count"] == usable
    assert result["automated_passed"] is (usable >= 7)
    assert len(result["evaluation_id"]) == 64
    assert result["evaluation_id"] == evaluation_id(result)
    assert result["comparison"] == {
        "status": "not_evaluated",
        "reason": "CANDIDATE_REPORT_UNAVAILABLE",
        "baseline_evaluation_id": result["evaluation_id"],
        "candidate_evaluation_id": None,
    }
    # This suite detects synthesized-note regressions; real-piano review is the release gate.
    assert result["evaluation"].startswith("Automated note matching")


def test_evaluation_comparison_reports_a_real_candidate_delta() -> None:
    baseline = {
        "automated_usable_count": 4,
        "model_version": "baseline",
        "evaluation_set_id": "fixed-set",
        "machine_summary": {"precision": 0.5, "recall": 0.8, "f1": 0.6, "structure_error_count": 2},
        "human_evaluation": {"status": "evaluated", "usable_count": 4},
    }
    candidate = {
        "automated_usable_count": 7,
        "model_version": "candidate",
        "evaluation_set_id": "fixed-set",
        "machine_summary": {
            "precision": 0.7,
            "recall": 0.9,
            "f1": 0.75,
            "structure_error_count": 0,
        },
        "human_evaluation": {"status": "evaluated", "usable_count": 7},
    }

    comparison = compare_evaluations(baseline, candidate)

    assert comparison["status"] == "evaluated"
    assert comparison["automated_usable_delta"] == 3
    assert comparison["machine_metric_deltas"] == {
        "precision": 0.2,
        "recall": 0.1,
        "f1": 0.15,
        "structure_error_count": -2.0,
    }
    assert comparison["human_usable_delta"] == 3
    assert comparison["baseline_evaluation_id"] == evaluation_id(baseline)
    assert comparison["candidate_evaluation_id"] == evaluation_id(candidate)


def test_evaluation_comparison_rejects_different_fixed_sets() -> None:
    baseline = {"automated_usable_count": 1, "evaluation_set_id": "set-a"}
    candidate = {"automated_usable_count": 9, "evaluation_set_id": "set-b"}

    assert compare_evaluations(baseline, candidate)["reason"] == "EVALUATION_SET_MISMATCH"


def test_evaluation_set_id_changes_when_truth_content_changes(tmp_path: Path) -> None:
    manifest = {"cases": [{"id": "same-count"}]}
    (tmp_path / "same-count.wav").write_bytes(b"fixed audio")
    reference = tmp_path / "same-count.mid"
    reference.write_bytes(b"same note count, pitch C")
    first = evaluation_set_id(manifest, tmp_path)

    reference.write_bytes(b"same note count, pitch D")

    assert evaluation_set_id(manifest, tmp_path) != first
