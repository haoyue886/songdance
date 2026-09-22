import json
import shutil
from pathlib import Path

import soundfile as sf

from app.pipeline.analysis import analyze_audio
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import transcribe_audio, write_raw_midi
from scripts.generate_regression_set import build_pattern, synthesize, write_midi

ROOT = Path(__file__).parents[1]
CONTRACT = ROOT / "tests/fixtures/audio/waltz-68-reference-manifest.json"
OUTPUT = ROOT / "tests/fixtures/audio/candidates/waltz-68-reference"


def run() -> None:
    manifest = json.loads(CONTRACT.read_text())
    case = manifest["case"]
    if manifest["status"] != "technical_candidate_rejected_pending_pitch_alignment":
        raise ValueError("waltz reference is not approved for candidate generation")
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    notes = build_pattern(case["pattern"])
    truth_midi = OUTPUT / "truth.mid"
    source_wav = OUTPUT / "source.wav"
    write_midi(notes, truth_midi)
    sf.write(
        source_wav,
        synthesize(
            notes,
            manifest["duration_seconds"],
            manifest["sample_rate"],
            manifest["noise"],
            False,
            manifest["synthesis_seed"],
        ),
        manifest["sample_rate"],
        subtype="PCM_16",
    )
    normalized = OUTPUT / "normalized.wav"
    preprocess_audio(source_wav, normalized)
    events, raw_midi = transcribe_audio(normalized)
    evidence = extract_harmonic_evidence(normalized, events)
    cleanup = clean_note_events(events, harmonic_evidence=evidence)
    analysis = analyze_audio(normalized)
    scored = build_score(
        cleanup.events,
        title=case["id"],
        analysis=analysis,
        harmonic_evidence=evidence,
        sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
        notation_context=None,
    )
    artifact = OUTPUT / "artifacts"
    artifact.mkdir()
    write_raw_midi(raw_midi, artifact / "raw.mid")
    write_quantized_midi(scored, artifact / "score.mid")
    write_musicxml(scored, artifact / "score.musicxml")
    (OUTPUT / "candidate-report.json").write_text(
        json.dumps(
            {
                "status": "technical_candidate_pending_pitch_alignment",
                "contract": manifest,
                "raw_event_count": len(events),
                "cleaned_event_count": len(cleanup.events),
                "analysis": analysis.summary(),
                "cleanup": cleanup.summary(),
                "reconstruction": scored.reconstruction,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {"output": str(OUTPUT), "raw": len(events), "cleaned": len(cleanup.events)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    run()
