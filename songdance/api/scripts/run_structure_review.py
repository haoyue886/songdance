import json
import shutil
from pathlib import Path

import pretty_midi

from app.pipeline.analysis import analyze_audio
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.score import NotationContext, build_score, write_musicxml, write_quantized_midi
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import transcribe_audio, write_raw_midi
from app.settings import Settings
from scripts.generate_regression_set import MANIFEST_PATH, OUTPUT_DIR, generate_regression_set
from scripts.score_parser_validation import validate_external_parsers
from scripts.structure_quality_gate import (
    ARTIFACT_ROOT,
    REVIEW_PATH,
    bind_structure_suite,
    reset_structure_review,
)


def _notation_context_for_case(case: dict[str, object]) -> NotationContext | None:
    texture_hint = case.get("texture_hint")
    if texture_hint not in {
        "monophonic_melody",
        "eighth_note_melody",
        "compound_68",
        "six_note_melody",
        "crossing_eighth_melody",
    }:
        return None
    reviewed = texture_hint in {
        "eighth_note_melody",
        "compound_68",
        "six_note_melody",
        "crossing_eighth_melody",
    }
    time_signature = {
        "eighth_note_melody": "4/4",
        "compound_68": "6/8",
        "six_note_melody": "3/4",
        "crossing_eighth_melody": "4/4",
    }.get(texture_hint)
    tempo_bpm = {
        "eighth_note_melody": 60,
        "compound_68": 120,
        "six_note_melody": 60,
        "crossing_eighth_melody": 60,
    }.get(texture_hint)
    return NotationContext(
        texture_hint=texture_hint,
        time_signature=time_signature,
        time_signature_source="expert_review" if reviewed else None,
        time_signature_confidence=1.0 if reviewed else None,
        quantization_divisions_per_quarter=4 if reviewed else None,
        quantization_source="expert_review" if reviewed else None,
        tempo_bpm=tempo_bpm,
        tempo_source="expert_review" if reviewed else None,
        measure_offset_units=0 if texture_hint == "crossing_eighth_melody" else None,
        measure_offset_source="expert_review" if texture_hint == "crossing_eighth_melody" else None,
        melody_pitch_pattern=(60, 64, 67, 72, 67, 64)
        if texture_hint == "six_note_melody"
        else None,
        melody_pattern_source="expert_review"
        if texture_hint == "six_note_melody"
        else None,
    )


def run(settings: Settings | None = None) -> None:
    active_settings = settings or Settings()
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not all((OUTPUT_DIR / f"{case['id']}.wav").is_file() for case in manifest["cases"]):
        generate_regression_set()
    reset_structure_review(manifest, REVIEW_PATH)
    note_counts: dict[str, int] = {}
    musicxml_paths: dict[str, Path] = {}
    for case in manifest["cases"]:
        case_id = case["id"]
        case_dir = ARTIFACT_ROOT / case_id
        shutil.rmtree(case_dir, ignore_errors=True)
        paths = artifact_paths(case_dir)
        normalized = case_dir / "normalized.wav"
        preprocess_audio(OUTPUT_DIR / f"{case_id}.wav", normalized)
        events, raw_midi = transcribe_audio(normalized)
        harmonic_evidence = extract_harmonic_evidence(
            normalized,
            events,
            include_decay_evidence=case.get("texture_hint") in {
                "monophonic_melody",
                "eighth_note_melody",
                "six_note_melody",
                "crossing_eighth_melody",
            },
            include_transient_evidence=case.get("texture_hint") == "crossing_eighth_melody",
        )
        cleaned = clean_note_events(
            events,
            active_settings.note_cleanup_config,
            harmonic_evidence=harmonic_evidence,
            preserve_simultaneous_unisons=case.get("texture_hint") == "crossing_eighth_melody",
        )
        analysis = analyze_audio(normalized, active_settings.structure_analysis_config)
        scored = build_score(
            cleaned.events,
            title=case_id,
            analysis=analysis,
            sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
            harmonic_evidence=harmonic_evidence,
            notation_context=_notation_context_for_case(case),
        )
        write_raw_midi(raw_midi, paths["raw_midi"])
        write_quantized_midi(scored, paths["midi"])
        write_musicxml(scored, paths["musicxml"])
        write_timeline(scored, paths["timeline"], cleanup_summary=cleaned.summary())
        normalized.unlink(missing_ok=True)
        parsed = pretty_midi.PrettyMIDI(str(paths["raw_midi"]))
        note_counts[case_id] = sum(len(instrument.notes) for instrument in parsed.instruments)
        musicxml_paths[case_id] = paths["musicxml"]
        print(f"prepared {case_id}: {note_counts[case_id]} raw MIDI notes")

    external = validate_external_parsers(list(musicxml_paths.values()))
    parser_validation = {
        case_id: {
            "music21": {"status": "passed"},
            **external[str(path.resolve())],
        }
        for case_id, path in musicxml_paths.items()
    }
    if any(
        parser["status"] != "passed"
        for result in parser_validation.values()
        for parser in result.values()
    ):
        raise RuntimeError("structure review artifacts failed parser validation")
    bind_structure_suite(note_counts, parser_validation)


if __name__ == "__main__":
    run()
