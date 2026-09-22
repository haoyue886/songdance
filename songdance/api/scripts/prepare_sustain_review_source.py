"""Prepare a new teacher-pattern fixture; never replace the historical four-note source."""

import argparse
import json
from pathlib import Path

import soundfile as sf

from scripts.generate_regression_set import SynthNote, synthesize, write_midi
from scripts.piano_comparison_cases import ROOT, file_sha256

CONTRACT = ROOT / "tests/fixtures/audio/sustain-triad-v2-manifest.json"
EXPECTED = [[55, 60, 64], [57, 60, 65], [55, 59, 62]]


def prepare(output: Path):
    manifest = json.loads(CONTRACT.read_text())
    case = manifest["case"]
    if case["chords_midi"] != EXPECTED or case["chords_scale_degrees"] != [
        "5-1-3",
        "6-1-4",
        "5-7-2",
    ]:
        raise ValueError("contract differs from teacher feedback")
    if (
        manifest["duration_seconds"] != 30
        or case["onset_interval_seconds"] != 2.0
        or case["note_duration_seconds"] != 1.6
    ):
        raise ValueError("fixture timing changed; review required")
    output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "production_eligible": False,
        "status": "running",
        "source_kind": "new_synthetic_teacher_pattern_not_original_audio",
        "contract_sha256": file_sha256(CONTRACT),
        "script_sha256": file_sha256(Path(__file__)),
        "generator_sha256": file_sha256(ROOT / "scripts/generate_regression_set.py"),
    }
    try:
        notes = [
            SynthNote(float(t), t + 1.6, pitch, 76)
            for t in range(0, 30, 2)
            for pitch in EXPECTED[(t // 2) % 3]
        ]
        write_midi(notes, output / "reference.mid")
        rate = manifest["sample_rate"]
        audio = synthesize(notes, 30, rate, case["noise"], False, case["synthesis_seed"])
        sf.write(output / "source.wav", audio, rate, subtype="PCM_16")
        receipt.update(
            status="source_prepared_not_transcribed",
            event_count=len(notes),
            onset_clusters=15,
            notes_per_cluster=3,
            artifacts={p.name: file_sha256(p) for p in output.iterdir() if p.is_file()},
            timing_scope=(
                "2s interval and 1.6s duration are fixture settings, not new teacher approval"
            ),
        )
    except Exception as error:
        receipt.update(status="failed", error=str(error))
        raise
    finally:
        (output / "source-receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output)["status"])
