import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import soundfile as sf

from app.pipeline.analysis import analyze_audio
from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.quality import evaluate_note_events
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import NoteEvent, transcribe_audio, write_raw_midi
from scripts.generate_regression_set import build_pattern, synthesize, write_midi

ROOT = Path(__file__).parents[1]
CONTRACT_PATH = ROOT / "tests/fixtures/audio/sustain-triad-v2-manifest.json"


def candidate_settings() -> dict[str, object]:
    manifest = json.loads(CONTRACT_PATH.read_text())
    if manifest.get("status") != "confirmed_by_expert_review":
        raise ValueError("sustain triad candidate requires confirmed expert truth")
    case = manifest["case"]
    return {
        "id": case["id"],
        "pattern": case["pattern"],
        "duration_seconds": manifest["duration_seconds"],
        "sample_rate": manifest["sample_rate"],
        "noise": case["noise"],
        "device_bandwidth": case["bandwidth"] == "device",
        "synthesis_seed": case["synthesis_seed"],
    }


def run() -> None:
    settings = candidate_settings()
    output = ROOT / "tests/fixtures/audio/candidates" / str(settings["id"])
    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    truth_notes = build_pattern(str(settings["pattern"]))
    truth_midi = output / "truth.mid"
    source_wav = output / "source.wav"
    write_midi(truth_notes, truth_midi)
    sample_rate = int(settings["sample_rate"])
    sf.write(
        source_wav,
        synthesize(
            truth_notes,
            float(settings["duration_seconds"]),
            sample_rate,
            float(settings["noise"]),
            bool(settings["device_bandwidth"]),
            int(settings["synthesis_seed"]),
        ),
        sample_rate,
        subtype="PCM_16",
    )
    normalized = output / "normalized.wav"
    preprocess_audio(source_wav, normalized)
    events, raw_midi = transcribe_audio(normalized)
    (output / "raw-events.json").write_text(
        json.dumps([asdict(event) for event in events], ensure_ascii=False, indent=2) + "\n"
    )
    evidence = extract_harmonic_evidence(normalized, events)
    cleaned = clean_note_events(events, harmonic_evidence=evidence)
    analysis = analyze_audio(normalized)
    scored = build_score(
        cleaned.events,
        title=str(settings["id"]),
        analysis=analysis,
        harmonic_evidence=evidence,
        sustain_evidence=extract_sustain_evidence(normalized, raw_midi),
    )
    paths = artifact_paths(output / "artifacts")
    write_raw_midi(raw_midi, paths["raw_midi"])
    write_quantized_midi(scored, paths["midi"])
    write_musicxml(scored, paths["musicxml"])
    write_timeline(scored, paths["timeline"], cleanup_summary=cleaned.summary())
    with TemporaryDirectory(prefix="sustain-triad-pdf-") as raw:
        pdf_root = Path(raw)
        case_root = pdf_root / str(settings["id"])
        case_root.mkdir()
        shutil.copy2(paths["musicxml"], case_root / "score.musicxml")
        web_root = ROOT.parent / "web"
        subprocess.run(
            [
                "node",
                str(web_root / "scripts/render-review-pdfs.mjs"),
                str(pdf_root),
            ],
            cwd=web_root,
            check=True,
        )
        shutil.copy2(case_root / "score.pdf", output / "artifacts/score.pdf")
    reference = [NoteEvent(n.start, n.end, n.pitch, 100, 1.0) for n in truth_notes]
    report = {
        "truth_note_count": len(reference),
        "raw_note_count": len(events),
        "cleaned_note_count": len(cleaned.events),
        "raw_metrics": evaluate_note_events(events, reference),
        "cleaned_metrics": evaluate_note_events(cleaned.events, reference),
        "cleanup": cleaned.summary(),
        "harmonic_evidence": evidence.summary(),
        "reconstruction": scored.reconstruction,
    }
    (output / "candidate-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    counts = {
        key: report[key] for key in ("truth_note_count", "raw_note_count", "cleaned_note_count")
    }
    print(json.dumps({"output": str(output), **counts}, ensure_ascii=False))


if __name__ == "__main__":
    run()
