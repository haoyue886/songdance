import json
from pathlib import Path

import soundfile as sf

from scripts.generate_regression_set import SynthNote, synthesize, write_midi

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "tests/fixtures/audio/short-value-manifest.json"
OUTPUT_DIR = MANIFEST_PATH.parent / "generated/short-values"


def generate_short_value_set() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    tempo = float(manifest["tempo_bpm"])
    duration = float(manifest["duration_seconds"])
    sample_rate = int(manifest["sample_rate"])
    quarter_seconds = 60 / tempo
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(manifest["cases"]):
        divisions = int(case["divisions_per_quarter"])
        step = quarter_seconds / divisions
        count = round(duration / step)
        notes = [SynthNote(0.0, duration, 48, 76)]
        notes.extend(
            SynthNote(
                item * step,
                min(duration, (item + 0.82) * step),
                (72, 74, 76, 77)[item % 4],
                88,
            )
            for item in range(count)
        )
        write_midi(notes, OUTPUT_DIR / f"{case['id']}.mid")
        audio = synthesize(
            notes,
            duration=duration,
            sample_rate=sample_rate,
            noise=0.0,
            device_bandwidth=False,
            seed=2_000 + index,
        )
        sf.write(
            OUTPUT_DIR / f"{case['id']}.wav",
            audio,
            sample_rate,
            subtype="PCM_16",
        )
        print(f"generated {case['id']}: {len(notes)} notes")


if __name__ == "__main__":
    generate_short_value_set()
