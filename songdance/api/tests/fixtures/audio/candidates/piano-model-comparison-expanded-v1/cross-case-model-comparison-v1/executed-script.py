"""Fresh Basic Pitch baseline on exactly the inputs used by Transkun."""

import json
from dataclasses import asdict
from pathlib import Path

from app.pipeline.transcribe import MODEL_VERSION, transcribe_audio, write_raw_midi
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256

CASES = ("06-sustain", "07-soft", "14-hand-crossing")


def run():
    source_root = BATCH_ROOT / "soundfont-cross-cases-v1"
    output = BATCH_ROOT / "cross-case-model-comparison-v1"
    output.mkdir(exist_ok=False)
    all_results = []
    for case in CASES:
        for variant in ("original", "soundfont"):
            source = source_root / case / variant
            dest = output / case / variant
            dest.mkdir(parents=True)
            status = dest / "status.json"
            status.write_text('{"status":"running"}')
            try:
                receipt_path = source / "transkun/inference.json"
                receipt = json.loads(receipt_path.read_text())
                audio = source / "padded.wav"
                transkun_midi = source / "transkun/raw.mid"
                if (
                    receipt["status"] != "inference_complete"
                    or receipt["input_sha256"] != file_sha256(audio)
                    or receipt["midi_sha256"] != file_sha256(transkun_midi)
                    or receipt["adapter_sha256"]
                    != file_sha256(ROOT / "experiments/models/transkun/run_cpu.py")
                    or receipt["manifest_sha256"]
                    != file_sha256(ROOT / "experiments/models/transkun/source_manifest.json")
                ):
                    raise ValueError("Transkun source provenance mismatch")
                events, midi = transcribe_audio(audio)
                write_raw_midi(midi, dest / "raw.mid")
                payload = [asdict(n) for n in events]
                (dest / "raw-events.json").write_text(json.dumps(payload, indent=2))
                basic, basic_clipped, basic_rejected = restore(payload, 1, 30)
                candidate, candidate_clipped, candidate_rejected = restore(
                    read_midi(transkun_midi), 1, 30
                )
                reference_path = ROOT / f"tests/fixtures/audio/generated/{case}.mid"
                original = read_midi(reference_path)
                reference = list({(n["start_sec"], n["pitch"]): n for n in original}.values())
                result = {
                    "production_eligible": False,
                    "case_id": case,
                    "variant": variant,
                    "basic_pitch_version": MODEL_VERSION,
                    "input_sha256": file_sha256(audio),
                    "reference_sha256": file_sha256(reference_path),
                    "source_reference_count": len(original),
                    "distinct_reference_count": len(reference),
                    "transkun_receipt_sha256": file_sha256(receipt_path),
                    "raw_midi_sha256": file_sha256(dest / "raw.mid"),
                    "raw_events_sha256": file_sha256(dest / "raw-events.json"),
                    "adapter_sha256": file_sha256(Path(__file__)),
                    "transcriber_sha256": file_sha256(ROOT / "app/pipeline/transcribe.py"),
                    "mapping_sha256": file_sha256(
                        ROOT / "scripts/evaluate_device_context_shift.py"
                    ),
                    "metric_sha256": file_sha256(ROOT / "scripts/compare_piano_model_outputs.py"),
                    "basic_clipped": basic_clipped,
                    "basic_rejected": basic_rejected,
                    "transkun_clipped": candidate_clipped,
                    "transkun_rejected": candidate_rejected,
                    "basic": {str(t): note_metrics(reference, basic, t) for t in (0.05, 0.1)},
                    "transkun": {
                        str(t): note_metrics(reference, candidate, t) for t in (0.05, 0.1)
                    },
                    "limitation": "synthetic sources, onset-only, no score quality or deployment approval",
                }
                (dest / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False))
                status.write_text('{"status":"complete"}')
                all_results.append(result)
                print(
                    case,
                    variant,
                    {
                        model: {
                            k: result[model]["0.05"][k]
                            for k in ["matched_count", "extra_count", "missing_count", "f1"]
                        }
                        for model in ("basic", "transkun")
                    },
                    flush=True,
                )
            except Exception as error:
                status.write_text(json.dumps({"status": "failed", "error": str(error)}))
                raise
    (output / "summary.json").write_text(json.dumps(all_results, indent=2))


if __name__ == "__main__":
    run()
