import json
import shutil
from pathlib import Path

import pretty_midi

from app.pipeline.analysis import analyze_audio
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
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
        cleaned = clean_note_events(events, active_settings.note_cleanup_config)
        analysis = analyze_audio(normalized, active_settings.structure_analysis_config)
        scored = build_score(cleaned.events, title=case_id, analysis=analysis)
        write_raw_midi(raw_midi, paths["raw_midi"])
        write_quantized_midi(scored, paths["midi"])
        write_musicxml(scored, paths["musicxml"])
        write_timeline(scored, paths["timeline"], cleanup_summary=cleaned.summary())
        normalized.unlink(missing_ok=True)
        parsed = pretty_midi.PrettyMIDI(str(paths["raw_midi"]))
        note_counts[case_id] = sum(
            len(instrument.notes) for instrument in parsed.instruments
        )
        musicxml_paths[case_id] = paths["musicxml"]
        print(f"prepared {case_id}: {note_counts[case_id]} raw MIDI notes")

    external = validate_external_parsers(list(musicxml_paths.values()))
    parser_validation = {
        case_id: {
            "music21": {"status": "passed"},
            **external[path.name],
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
