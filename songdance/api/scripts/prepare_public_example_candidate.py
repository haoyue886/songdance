"""Prepare a provenance-bound candidate for the public-example review gate."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pretty_midi
from music21 import converter, key, meter

from app.pipeline.analysis import AnalysisConfig, analyze_audio
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import HarmonicEvidenceConfig, extract_harmonic_evidence
from app.pipeline.notation_context import NotationContext
from app.pipeline.score import (
    build_score,
    read_musicxml_structure,
    write_musicxml,
    write_quantized_midi,
)
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import MODEL_VERSION, transcribe_audio, write_raw_midi
from scripts.human_quality_gate import file_sha256
from scripts.score_parser_validation import validate_external_parsers

API_ROOT = Path(__file__).parents[1]
CANDIDATE_ROOT = API_ROOT / "tests/fixtures/audio/public-example-candidates/petzold-minuet"
SOURCE_AUDIO = CANDIDATE_ROOT / "source.wav"
REFERENCE_MIDI = CANDIDATE_ROOT / "reference.mid"
REFERENCE_PDF = CANDIDATE_ROOT / "reference.pdf"
CANDIDATE_MANIFEST = CANDIDATE_ROOT / "candidate.json"
CANDIDATE_ID = "petzold-minuet-bwv-anh-114"
TITLE = "Christian Petzold - Minuet in G major, BWV Anh.114"


def prepare() -> dict[str, object]:
    if not SOURCE_AUDIO.is_file() or not REFERENCE_MIDI.is_file() or not REFERENCE_PDF.is_file():
        raise FileNotFoundError("candidate source, MIDI, and PDF must be downloaded first")

    paths = artifact_paths(CANDIDATE_ROOT)
    normalized = CANDIDATE_ROOT / ".normalized.wav"
    preprocess_audio(SOURCE_AUDIO, normalized)
    events, raw_midi = transcribe_audio(normalized)
    harmonic_evidence = extract_harmonic_evidence(
        normalized,
        events,
        HarmonicEvidenceConfig(
            bass_priority_enabled=True,
            bass_priority_source="human_review",
        ),
    )
    cleanup = clean_note_events(
        events,
        config=None,
        harmonic_evidence=harmonic_evidence,
    )
    analysis = analyze_audio(
        normalized,
        AnalysisConfig(max_duration_seconds=90.0),
    )
    scored = build_score(
        cleanup.events,
        title=TITLE,
        analysis=analysis,
        sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
        harmonic_evidence=harmonic_evidence,
        notation_context=NotationContext(
            key_signature="G major",
            key_signature_source="reference_score",
            key_signature_confidence=1.0,
            time_signature="3/4",
            time_signature_source="reference_score",
            time_signature_confidence=1.0,
            measure_offset_units=0,
            measure_offset_source="reference_score",
            quantization_divisions_per_quarter=4,
            quantization_source="reference_score",
            ornamentation_expected=True,
            ornamentation_source="human_review",
        ),
    )
    write_raw_midi(raw_midi, paths["raw_midi"])
    write_quantized_midi(scored, paths["midi"])
    write_musicxml(scored, paths["musicxml"])
    write_timeline(scored, paths["timeline"], cleanup_summary=cleanup.summary())
    normalized.unlink(missing_ok=True)

    raw_midi_notes = sum(
        len(instrument.notes)
        for instrument in pretty_midi.PrettyMIDI(str(paths["raw_midi"])).instruments
    )
    reference = _reference_summary()
    structure = read_musicxml_structure(paths["musicxml"])
    external = validate_external_parsers([paths["musicxml"]])[str(paths["musicxml"].resolve())]
    artifacts = {
        kind: {
            "path": path.name,
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for kind, path in {
            "raw_midi": paths["raw_midi"],
            "midi": paths["midi"],
            "musicxml": paths["musicxml"],
            "timeline": paths["timeline"],
        }.items()
    }
    manifest = {
        "schema_version": 1,
        "candidate_id": CANDIDATE_ID,
        "status": "candidate_rejected",
        "title": TITLE,
        "composer": "Christian Petzold (formerly attributed to J.S. Bach)",
        "performer": "KasraR",
        "source": {
            "source_page": "https://commons.wikimedia.org/wiki/File:Minuet-G-Major-BWV-Anh-114.ogv",
            "download_url": "https://upload.wikimedia.org/wikipedia/commons/7/7d/Minuet-G-Major-BWV-Anh-114.ogv",
            "license": "CC BY-SA 3.0 with public-domain dedication",
            "license_url": "https://creativecommons.org/licenses/by-sa/3.0/deed.en",
            "rights_note": (
                "Wikimedia Commons page identifies the work as an own digital-piano "
                "performance by KasraR."
            ),
            "clip_start_sec": 0.0,
            "clip_duration_sec": _duration_seconds(SOURCE_AUDIO),
            "clip_sha256": file_sha256(SOURCE_AUDIO),
        },
        "reference_score": {
            "source_page": "https://pianovera.com/en/midi/menuet-en-sol/",
            "midi_download_url": "https://pianovera.com/midi/files/menuet-en-sol.mid",
            "pdf_download_url": "https://pianovera.com/midi/files/menuet-en-sol-piano-sheet.pdf",
            "provider": "Pianovera / Mutopia Project",
            "license": "Public domain",
            "license_url": "https://www.mutopiaproject.org/",
            "midi_sha256": file_sha256(REFERENCE_MIDI),
            "pdf_sha256": file_sha256(REFERENCE_PDF),
            **reference,
        },
        "artifacts": artifacts,
        "pipeline": {
            "model_version": MODEL_VERSION,
            "postprocess_version": str(
                json.loads(paths["timeline"].read_text(encoding="utf-8"))["postprocess_version"]
            ),
            "raw_midi_note_count": raw_midi_notes,
            "analysis": analysis.summary(),
            "notation": scored.notation.summary(),
            "analysis_override": json.loads(paths["timeline"].read_text(encoding="utf-8")).get(
                "analysis_override"
            ),
            "cleanup": cleanup.summary(),
            "structure": structure,
            "parser_validation": external,
        },
        "review": {
            "rating": "needs_redo",
            "reviewed_at": "2026-08-22T00:00:00+08:00",
            "notes": (
                "人工评审判定装饰音占用正拍并引发节奏偏移，且低音自然泛音被误写为独立高音；"
                "该候选不得作为初级公开示例。"
            ),
            "findings": [
                {
                    "code": "ORNAMENT_DURATION_SHIFT",
                    "summary": "装饰音未按不占正拍的记号处理，导致后续节奏位置偏移。",
                },
                {
                    "code": "BASS_HARMONIC_FALSE_POSITIVE",
                    "summary": "低音基频的自然泛音被误识别为独立高音。",
                },
                {
                    "code": "CANDIDATE_TEXTURE_TOO_COMPLEX",
                    "summary": (
                        "巴洛克装饰音与复调超出当前初级能力阶梯，"
                        "下一候选优先核验哈农公式化练习。"
                    ),
                },
            ],
        },
    }
    CANDIDATE_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _reference_summary() -> dict[str, object]:
    score = converter.parse(REFERENCE_MIDI)
    parts = list(score.parts)
    measures = [list(part.getElementsByClass("Measure")) for part in parts]
    key_signatures = list(score.recurse().getElementsByClass(key.KeySignature))
    time_signatures = list(score.recurse().getElementsByClass(meter.TimeSignature))
    notes = list(score.recurse().notes)
    return {
        "format": "midi",
        "parts": len(parts),
        "measure_count": len(measures[0]) if measures else 0,
        "measure_counts_by_part": [len(items) for items in measures],
        "notation_key_signature": sorted({item.asKey().name for item in key_signatures}),
        "key_signature_fifths": sorted({item.sharps for item in key_signatures}),
        "time_signature": sorted({item.ratioString for item in time_signatures}),
        "duration_quarter_length": float(score.duration.quarterLength),
        "note_count": len(notes),
        "shortest_note_quarter_length": min(float(item.duration.quarterLength) for item in notes),
        "shortest_note_value": 16,
    }


def _duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        return round(source.getnframes() / source.getframerate(), 6)


if __name__ == "__main__":
    result = prepare()
    print(
        json.dumps(
            {"candidate_id": result["candidate_id"], "status": result["status"]},
            ensure_ascii=False,
        )
    )
