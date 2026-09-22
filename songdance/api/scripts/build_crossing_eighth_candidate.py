"""Build only the crossing candidate. Never refresh shared reviews or release bundles."""

import argparse
import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import pretty_midi

from app.pipeline.analysis import analyze_audio
from app.pipeline.artifacts import artifact_paths, write_raw_timeline, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.crossing_eighth import select_crossing_eighth_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.quality import evaluate_note_events
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import MODEL_VERSION, NoteEvent, transcribe_audio, write_raw_midi
from scripts.crossing_candidate_validation import validate_saved_outputs
from scripts.human_quality_gate import PIPELINE_FILES
from scripts.run_structure_review import _notation_context_for_case
from scripts.score_parser_validation import validate_external_parsers

ROOT = Path(__file__).parents[1]
CASE_ID = "14-hand-crossing"
FIXTURES = ROOT / "tests/fixtures/audio"
SOURCE_WAV = FIXTURES / "generated" / f"{CASE_ID}.wav"
SOURCE_MIDI = SOURCE_WAV.with_suffix(".mid")
OUTPUT_DIR = FIXTURES / "candidates" / f"{CASE_ID}-tail-v2"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    files = [ROOT / "app/pipeline" / name for name in PIPELINE_FILES]
    files.extend([Path(__file__), ROOT / "scripts/crossing_candidate_validation.py",
                  ROOT / "scripts/run_structure_review.py"])
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in files}


def run(output_dir: Path = OUTPUT_DIR) -> dict[str, object]:
    case = next(c for c in json.loads((FIXTURES / "manifest.json").read_text())["cases"]
                if c["id"] == CASE_ID)
    if case.get("texture_hint") != "crossing_eighth_melody":
        raise ValueError("crossing candidate requires the reviewed fixture context")
    if not SOURCE_WAV.is_file() or not SOURCE_MIDI.is_file():
        raise FileNotFoundError("missing frozen crossing WAV/MIDI")
    output_dir.mkdir(parents=True, exist_ok=True)
    copied = output_dir / SOURCE_WAV.name
    shutil.copy2(SOURCE_WAV, copied)
    normalized = output_dir / "normalized.wav"
    preprocess_audio(copied, normalized)
    events, raw_midi = transcribe_audio(normalized)
    (output_dir / "raw-events.json").write_text(
        json.dumps([asdict(e) for e in events], ensure_ascii=False, indent=2) + "\n"
    )
    evidence = extract_harmonic_evidence(
        normalized, events, include_decay_evidence=True, include_transient_evidence=True
    )
    cleaned = clean_note_events(
        events, harmonic_evidence=evidence, preserve_simultaneous_unisons=True
    )
    analysis = analyze_audio(normalized)
    scored = build_score(
        cleaned.events, title=CASE_ID, analysis=analysis, harmonic_evidence=evidence,
        sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
        notation_context=_notation_context_for_case(case),
    )
    paths = artifact_paths(output_dir / "artifacts")
    write_raw_midi(raw_midi, paths["raw_midi"])
    write_raw_timeline(events, paths["raw_timeline"])
    write_quantized_midi(scored, paths["midi"])
    write_musicxml(scored, paths["musicxml"])
    write_timeline(scored, paths["timeline"], cleanup_summary=cleaned.summary())
    validation = validate_saved_outputs(paths)
    parsers = validate_external_parsers([paths["musicxml"]])[str(paths["musicxml"].resolve())]
    # Reference pitches are evaluation-only; the scorer never receives them.
    source = pretty_midi.PrettyMIDI(str(SOURCE_MIDI))
    reference_notes = [n for instrument in source.instruments for n in instrument.notes]
    acoustic_truth = {(n.start, n.pitch): n for n in reference_notes}
    reference = [NoteEvent(n.start, n.end, n.pitch, n.velocity, 1.0)
                 for n in acoustic_truth.values()]
    metrics = evaluate_note_events(scored.notation_notes, reference)
    baseline, _ = select_crossing_eighth_events(cleaned.events, 60.0 / scored.tempo_bpm, evidence)
    baseline_metrics = evaluate_note_events(baseline, reference)
    tail_evaluation = {
        "baseline_notation_count": len(baseline),
        "baseline_metrics": baseline_metrics,
        "removed_tail_event_count": scored.reconstruction["crossing_tail_cleanup"]["removed_count"],
        "correct_onsets_preserved": (
            metrics["matched_note_count"] == baseline_metrics["matched_note_count"]
        ),
        "extra_event_reduction": (
            len(baseline) - baseline_metrics["matched_note_count"]
            - (len(scored.notation_notes) - metrics["matched_note_count"])
        ),
    }
    report = {
        "case_id": CASE_ID, "status": "candidate_needs_review", "human_rating": "pending",
        "production_eligible": False, "model_version": MODEL_VERSION,
        "source_sha256": file_sha256(SOURCE_WAV),
        "source_midi_sha256": file_sha256(SOURCE_MIDI), "case_context": case,
        "code_sha256": code_hashes(),
        "raw_note_count": len(events), "cleaned_note_count": len(cleaned.events),
        "notation_note_count": len(scored.notation_notes),
        "tempo_bpm": scored.tempo_bpm, "detected_bpm": analysis.bpm,
        "time_signature": scored.analysis.time_signature,
        "crossing_eighth_cleanup": scored.reconstruction["crossing_eighth_cleanup"],
        "crossing_tail_cleanup": scored.reconstruction["crossing_tail_cleanup"],
        "tail_evaluation": tail_evaluation,
        "saved_output_validation": validation, "parser_validation": parsers,
        "reference": {
            "source_midi_note_count": len(reference_notes),
            "distinct_pitch_onsets": len(reference),
            "onset_group_count": len({n.start for n in reference_notes}),
            "comparison": "unique sounding pitch/onset; same-key unisons counted once",
            "metrics": metrics,
            "unmatched_output_events": (
                metrics["estimated_note_count"] - metrics["matched_note_count"]
            ),
            "missing_reference_events": (
                metrics["reference_note_count"] - metrics["matched_note_count"]
            ),
        },
        "artifacts_sha256": {p.name: file_sha256(p) for p in paths.values()},
    }
    (output_dir / "candidate-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps({k: report[k] for k in (
        "status", "raw_note_count", "cleaned_note_count", "notation_note_count",
        "tempo_bpm", "detected_bpm", "reference",
    )}, ensure_ascii=False))
    if validation["status"] != "passed" or any(p["status"] != "passed" for p in parsers.values()):
        raise RuntimeError("crossing candidate validation failed; see candidate-report.json")
    if (
        not tail_evaluation["correct_onsets_preserved"]
        or tail_evaluation["extra_event_reduction"] <= 0
    ):
        raise RuntimeError("crossing tail cleanup did not improve without lost onsets; see report")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    run(parser.parse_args().output_dir)
