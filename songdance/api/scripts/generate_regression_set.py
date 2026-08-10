import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pretty_midi
import soundfile as sf
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "tests/fixtures/audio/manifest.json"
OUTPUT_DIR = MANIFEST_PATH.parent / "generated"


@dataclass(frozen=True)
class SynthNote:
    start: float
    end: float
    pitch: int
    velocity: int


def generate_regression_set() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for index, case in enumerate(manifest["cases"]):
        notes = build_pattern(case["pattern"])
        write_midi(notes, OUTPUT_DIR / f"{case['id']}.mid")
        audio = synthesize(
            notes,
            duration=float(manifest["duration_seconds"]),
            sample_rate=int(manifest["sample_rate"]),
            noise=float(case["noise"]),
            device_bandwidth=case["bandwidth"] == "device",
            seed=1_000 + index,
        )
        sf.write(OUTPUT_DIR / f"{case['id']}.wav", audio, manifest["sample_rate"], subtype="PCM_16")
        print(f"generated {case['id']}: {len(notes)} notes")


def build_pattern(name: str) -> list[SynthNote]:
    builders = {
        "slow_melody": slow_melody,
        "fast_scale": fast_scale,
        "block_chords": block_chords,
        "arpeggios": arpeggios,
        "two_hand": two_hand,
        "sustain": sustained_chords,
        "soft": soft_melody,
        "dynamics": dynamic_melody,
        "waltz_34": waltz_34,
        "compound_68": compound_68,
        "key_change": key_change,
        "hand_crossing": hand_crossing,
        "repeated_notes": repeated_notes,
        "noisy_polyphony": noisy_polyphony,
    }
    return builders[name]()


def slow_melody() -> list[SynthNote]:
    pitches = [60, 62, 64, 67, 69, 67, 64, 62]
    return sequence(pitches, step=1.0, length=0.82, velocity=86)


def fast_scale() -> list[SynthNote]:
    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65, 64, 62]
    return sequence(pitches, step=0.25, length=0.21, velocity=92)


def block_chords() -> list[SynthNote]:
    chords = [[48, 60, 64, 67], [50, 62, 65, 69], [43, 59, 62, 67], [48, 60, 64, 67]]
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29.5, 1.5)):
        notes.extend(
            SynthNote(float(start), float(start + 1.2), pitch, 88) for pitch in chords[index % 4]
        )
    return notes


def arpeggios() -> list[SynthNote]:
    pitches = [48, 55, 60, 64, 67, 72, 67, 64]
    return sequence(pitches, step=0.25, length=0.42, velocity=82)


def two_hand() -> list[SynthNote]:
    right = sequence([60, 64, 67, 72, 69, 67, 64, 62], step=0.5, length=0.42, velocity=88)
    left = [
        SynthNote(float(start), float(start + 0.85), [36, 41, 43, 36][index % 4], 78)
        for index, start in enumerate(np.arange(0, 29.5, 1.0))
    ]
    return sorted([*right, *left], key=lambda item: (item.start, item.pitch))


def sustained_chords() -> list[SynthNote]:
    chords = [[48, 55, 60, 64], [41, 57, 60, 65], [43, 55, 59, 62]]
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29, 2.0)):
        notes.extend(
            SynthNote(float(start), min(30.0, float(start + 2.8)), pitch, 76)
            for pitch in chords[index % 3]
        )
    return notes


def soft_melody() -> list[SynthNote]:
    return sequence([72, 71, 69, 67, 64, 67, 69, 71], step=0.75, length=0.62, velocity=38)


def dynamic_melody() -> list[SynthNote]:
    pitches = [60, 62, 64, 65, 67, 69, 71, 72]
    velocities = [35, 50, 68, 86, 108, 92, 65, 44]
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29.5, 0.5)):
        notes.append(
            SynthNote(
                float(start),
                float(start + 0.42),
                pitches[index % len(pitches)],
                velocities[index % len(velocities)],
            )
        )
    return notes


def waltz_34() -> list[SynthNote]:
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29.25, 1.5)):
        root = [48, 53, 55, 50][index % 4]
        notes.append(SynthNote(float(start), float(start + 1.2), root, 78))
        notes.extend(
            SynthNote(float(start + offset), float(start + offset + 0.38), pitch, 84)
            for offset, pitch in ((0.5, root + 12), (1.0, root + 16))
        )
    return notes


def compound_68() -> list[SynthNote]:
    pattern = [60, 64, 67, 69, 67, 64]
    notes = sequence(pattern, step=0.25, length=0.21, velocity=84)
    notes.extend(
        SynthNote(float(start), float(start + 1.35), [36, 41, 43][index % 3], 74)
        for index, start in enumerate(np.arange(0, 29.0, 1.5))
    )
    return sorted(notes, key=lambda item: (item.start, item.pitch))


def key_change() -> list[SynthNote]:
    first = sequence([60, 64, 67, 72, 67, 64], step=0.5, length=0.42, velocity=86)
    second = [
        SynthNote(note.start + 15.0, min(30.0, note.end + 15.0), note.pitch + 2, note.velocity)
        for note in first
        if note.start < 15.0
    ]
    return [*first, *second]


def hand_crossing() -> list[SynthNote]:
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29.5, 0.5)):
        left_pitch = 48 + (index % 8) * 3
        right_pitch = 72 - (index % 8) * 3
        notes.append(SynthNote(float(start), float(start + 0.65), left_pitch, 78))
        notes.append(SynthNote(float(start), float(start + 0.42), right_pitch, 88))
    return sorted(notes, key=lambda item: (item.start, item.pitch))


def repeated_notes() -> list[SynthNote]:
    notes: list[SynthNote] = []
    for index, start in enumerate(np.arange(0, 29.5, 0.25)):
        pitch = [60, 60, 62, 62, 64, 64, 67, 67][index % 8]
        notes.append(SynthNote(float(start), float(start + 0.16), pitch, 90))
    return notes


def noisy_polyphony() -> list[SynthNote]:
    return sustained_chords() + sequence([72, 74, 76, 79, 76, 74], 0.5, 0.38, 78)


def sequence(pitches: list[int], step: float, length: float, velocity: int) -> list[SynthNote]:
    return [
        SynthNote(
            float(start), min(30.0, float(start + length)), pitches[index % len(pitches)], velocity
        )
        for index, start in enumerate(np.arange(0, 29.75, step))
    ]


def write_midi(notes: list[SynthNote], destination: Path) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0, name="Regression Grand Piano")
    piano.notes = [
        pretty_midi.Note(note.velocity, note.pitch, note.start, note.end) for note in notes
    ]
    midi.instruments.append(piano)
    midi.write(str(destination))


def synthesize(
    notes: list[SynthNote],
    duration: float,
    sample_rate: int,
    noise: float,
    device_bandwidth: bool,
    seed: int,
) -> np.ndarray:
    audio = np.zeros(round(duration * sample_rate), dtype=np.float32)
    for item in notes:
        start = round(item.start * sample_rate)
        audible_length = min(duration - item.start, item.end - item.start + 0.8)
        times = np.arange(round(audible_length * sample_rate), dtype=np.float32) / sample_rate
        frequency = 440.0 * 2 ** ((item.pitch - 69) / 12)
        envelope = np.minimum(1, times / 0.008) * np.exp(-2.6 * times)
        tone = np.zeros_like(times)
        for harmonic in range(1, 7):
            if frequency * harmonic >= sample_rate / 2:
                break
            inharmonic = harmonic * math.sqrt(1 + 0.00025 * harmonic * harmonic)
            tone += np.sin(2 * np.pi * frequency * inharmonic * times) / harmonic**1.35
        tone *= envelope * (item.velocity / 127)
        end = min(len(audio), start + len(tone))
        audio[start:end] += tone[: end - start]
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio * (0.82 / peak)
    if device_bandwidth:
        audio = sosfilt(
            butter(4, [180, 5_500], btype="bandpass", fs=sample_rate, output="sos"), audio
        )
    if noise:
        audio += np.random.default_rng(seed).normal(0, noise, size=audio.shape).astype(np.float32)
    return np.clip(audio, -1, 1)


if __name__ == "__main__":
    generate_regression_set()
