import json
import shutil

import pretty_midi

from app.pipeline.analysis import analyze_audio
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import transcribe_audio, write_raw_midi
from app.settings import Settings
from scripts.human_quality_gate import (
    bind_generated_suite,
    record_raw_midi_note_counts,
    reset_review,
)
from scripts.prepare_human_regression_set import FIXTURE_ROOT, OUTPUT_DIR, prepare

REVIEW_DIR = FIXTURE_ROOT / "human-review-artifacts"
REVIEW_PATH = FIXTURE_ROOT / "human-review.json"


def run(settings: Settings | None = None) -> None:
    active_settings = settings or Settings()
    manifest = json.loads((FIXTURE_ROOT / "human-manifest.json").read_text(encoding="utf-8"))
    if not all((OUTPUT_DIR / f"{case['id']}.wav").is_file() for case in manifest["cases"]):
        prepare()
    reset_review(manifest, REVIEW_PATH)
    raw_midi_note_counts: dict[str, int] = {}
    for case in manifest["cases"]:
        case_dir = REVIEW_DIR / case["id"]
        shutil.rmtree(case_dir, ignore_errors=True)
        paths = artifact_paths(case_dir)
        normalized = case_dir / "normalized.wav"
        preprocess_audio(OUTPUT_DIR / f"{case['id']}.wav", normalized)
        events, raw_midi = transcribe_audio(
            normalized,
            onset_threshold=active_settings.model_onset_threshold,
            frame_threshold=active_settings.model_frame_threshold,
        )
        cleanup_result = clean_note_events(
            events,
            active_settings.note_cleanup_config,
            harmonic_evidence=extract_harmonic_evidence(normalized, events),
        )
        structure_analysis = analyze_audio(normalized, active_settings.structure_analysis_config)
        scored = build_score(
            cleanup_result.events,
            title=case["id"],
            analysis=structure_analysis,
            sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
        )
        write_raw_midi(raw_midi, paths["raw_midi"])
        parsed_raw_midi = pretty_midi.PrettyMIDI(str(paths["raw_midi"]))
        raw_midi_note_counts[case["id"]] = sum(
            len(instrument.notes) for instrument in parsed_raw_midi.instruments
        )
        write_quantized_midi(scored, paths["midi"])
        write_musicxml(scored, paths["musicxml"])
        write_timeline(scored, paths["timeline"], cleanup_summary=cleanup_result.summary())
        print(f"transcribed {case['id']}: {raw_midi_note_counts[case['id']]} raw MIDI notes")
    record_raw_midi_note_counts(raw_midi_note_counts, REVIEW_PATH)
    bind_generated_suite(REVIEW_PATH, FIXTURE_ROOT)


if __name__ == "__main__":
    run()
