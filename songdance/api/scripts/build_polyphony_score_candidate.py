"""Explicit meter score preview with count gates; not a corrected triad transcription."""

import argparse
import json
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from app.pipeline.artifacts import write_timeline
from app.pipeline.score import NotationContext, build_score, write_musicxml, write_quantized_midi
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256
from scripts.validate_polyphony_preview import validate

SOURCE = ROOT / "tests/fixtures/audio/candidates/16-meter-only-v1"


def run(output):
    source_report = json.loads((SOURCE / "audit.json").read_text())
    raw = SOURCE / "candidate.mid"
    if file_sha256(raw) != source_report["midi_sha256"]:
        raise ValueError("source MIDI changed")
    original = read_midi(raw)
    events = [
        NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], 0.0) for n in original
    ]
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "production_eligible": False,
        "status": "running",
        "source_sha256": file_sha256(raw),
        "source_audit_sha256": file_sha256(SOURCE / "audit.json"),
        "builder_sha256": file_sha256(Path(__file__)),
        "configuration": "operator 2/4, 60 BPM, zero bar origin, sixteenth grid",
        "confidence_semantics": "zero internal placeholder, not inferred certainty",
        "unresolved": source_report["unresolved"],
    }
    try:
        context = NotationContext(
            time_signature="2/4",
            time_signature_source="teacher_meter_hypothesis",
            time_signature_confidence=0.0,
            key_signature="C major",
            key_signature_source="operator_display_default_not_inferred",
            key_signature_confidence=0.0,
            tempo_bpm=60,
            tempo_source="explicit_notation_equivalence",
            measure_offset_units=0,
            measure_offset_source="operator_assumption",
            quantization_divisions_per_quarter=4,
            quantization_source="operator_grid_hypothesis",
        )
        scored = build_score(events, title="16 - 2/4 review candidate", notation_context=context)
        scored = replace(
            scored,
            analysis=replace(scored.analysis, bpm_confidence=0.0, time_signature_confidence=0.0),
        )
        report["field_semantics"] = {
            "note_confidence": "unknown; numeric zero required by existing score API",
            "meter": "explicit hypothesis, not model probability",
            "key": "display default, not inferred",
            "hand_confidence": "existing uncalibrated layout heuristic, not actual hand certainty",
        }
        expected = Counter(n.pitch for n in events)
        if Counter(n.pitch for n in scored.notation_notes) != expected:
            raise ValueError("score construction changed pitch multiplicity; candidate rejected")
        if any(n.end_sec <= n.start_sec for n in scored.notation_notes):
            raise ValueError("nonpositive score duration")
        write_musicxml(scored, output / "score.musicxml")
        write_quantized_midi(scored, output / "score.mid")
        write_timeline(
            scored, output / "timeline.json", model_version="basic-pitch-raw-meter-candidate"
        )
        parsed = read_midi(output / "score.mid")
        if Counter(n["pitch"] for n in parsed) != expected:
            raise ValueError("exported MIDI changed note multiplicity")
        consistency = validate(
            output / "score.musicxml",
            output / "score.mid",
            scored.notation_notes,
            60 / scored.tempo_bpm,
        )
        report["export_consistency"] = consistency
        report["artifacts"] = {
            name: file_sha256(output / name)
            for name in ("score.musicxml", "score.mid", "timeline.json")
        }
        if consistency["status"] != "passed":
            raise ValueError("MusicXML/MIDI event mismatch; preview must not be accepted")
        report.update(
            status="preview_needs_review",
            input_count=len(events),
            output_count=len(parsed),
            structure=read_musicxml_structure(output / "score.musicxml"),
            input_events=original,
            notated_events=[asdict(n) for n in scored.notation_notes],
            artifacts={
                name: file_sha256(output / name)
                for name in ("score.musicxml", "score.mid", "timeline.json")
            },
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(run(parser.parse_args().output)["status"])
