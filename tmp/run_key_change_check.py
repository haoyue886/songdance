import json
import tempfile
from pathlib import Path

from app.pipeline.analysis import analyze_audio
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.melody_cleanup import clean_melody_tails
from app.pipeline.adaptive_quantization import select_quantization
from app.pipeline.quantize import quantize_events, seconds_per_quarter
from app.pipeline.score import build_score
from app.pipeline.transcribe import transcribe_audio
from scripts.run_structure_review import _notation_context_for_case


def main() -> None:
    root = Path("tests/fixtures/audio")
    manifest = json.loads((root / "manifest.json").read_text())
    case = next(item for item in manifest["cases"] if item["id"] == "13-key-change")
    with tempfile.TemporaryDirectory() as directory:
        normalized = Path(directory) / "normalized.wav"
        preprocess_audio(root / "generated/13-key-change.wav", normalized)
        events, _ = transcribe_audio(normalized)
        evidence = extract_harmonic_evidence(
            normalized, events, include_decay_evidence=True
        )
        cleaned = clean_note_events(events, harmonic_evidence=evidence)
        analysis = analyze_audio(normalized)
        context = _notation_context_for_case(case)
        melody = clean_melody_tails(
            cleaned.events, evidence, enabled=True
        )
        quantization = select_quantization(
            melody.events,
            analysis,
            forced_divisions_per_quarter=context.quantization_divisions_per_quarter,
            source=context.quantization_source,
        )
        quantized = quantize_events(
            melody.events, analysis, quantization, cap_melody_durations=False
        )
        slot_seconds = 0.5
        origin = min(event.start_sec for event in quantized)
        groups = {}
        for event in quantized:
            slot = round((event.start_sec - origin) / slot_seconds)
            if abs(event.start_sec - (origin + slot * slot_seconds)) <= slot_seconds * 0.42:
                groups.setdefault(slot, []).append(event)
        competing = [items for items in groups.values() if len(items) > 1]
        evidence_classes = {"independent": 0, "non_independent": 0, "unknown": 0}
        competing_details = []
        for items in competing:
            detail = []
            for event in items:
                matches = [item for item in evidence.onset_observations if item.matches(event)]
                if len(matches) != 1:
                    evidence_classes["unknown"] += 1
                    onset = "unknown"
                elif matches[0].independent_onset:
                    evidence_classes["independent"] += 1
                    onset = "independent"
                else:
                    evidence_classes["non_independent"] += 1
                    onset = "non_independent"
                harmonic = [
                    {
                        "fundamental": item.fundamental_pitch,
                        "energy_ratio": item.energy_ratio,
                        "independent": item.independent_onset,
                        "velocity_ratio": item.velocity_ratio,
                    }
                    for item in evidence.observations
                    if item.harmonic_pitch == event.pitch
                    and abs(item.harmonic_start_sec - event.start_sec) <= 0.08
                ]
                detail.append(
                    {
                        "pitch": event.pitch,
                        "velocity": event.velocity,
                        "confidence": round(event.confidence, 3),
                        "onset": onset,
                        "harmonic": harmonic,
                    }
                )
            competing_details.append(detail)
        scored = build_score(
            cleaned.events,
            analysis=analysis,
            harmonic_evidence=evidence,
            notation_context=context,
        )
        print(
            json.dumps(
                {
                    "raw_events": len(events),
                    "cleaned_events": len(cleaned.events),
                    "notation_notes": len(scored.notation_notes),
                    "time_signature": scored.analysis.time_signature,
                    "tempo": scored.tempo_bpm,
                    "staff": scored.reconstruction["staff_layout"]["value"],
                    "chords": scored.reconstruction["chord_count"],
                    "voices": scored.reconstruction["voice_count"],
                    "slot_cleanup": scored.reconstruction["six_note_melody_cleanup"],
                    "melody_cleanup": scored.reconstruction["melody_cleanup"],
                    "competing_slots": len(competing),
                    "competing_candidates": sum(len(items) for items in competing),
                    "evidence_classes": evidence_classes,
                    "competing_details": competing_details,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
