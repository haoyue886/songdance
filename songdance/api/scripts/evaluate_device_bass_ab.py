import hashlib
import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt, welch

from app.pipeline.analysis import analyze_audio
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.quality import evaluate_note_events
from app.pipeline.quantize import seconds_per_quarter
from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_validation import score_structure_summary
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import MODEL_VERSION, NoteEvent, transcribe_audio
from scripts.generate_regression_set import SynthNote, build_pattern, synthesize, write_midi
from scripts.human_quality_gate import PIPELINE_FILES

ROOT = Path(__file__).parents[1]
MANIFEST_PATH = ROOT / "tests/fixtures/audio/device-bass-ab-manifest.json"
OUTPUT = ROOT / "tests/fixtures/audio/candidates/device-bass-ab"
ONSET_TOLERANCE_SECONDS = 0.1
SCORE_ONSET_TOLERANCE_SECONDS = 0.13


def evaluate() -> dict[str, object]:
    manifest = _read_json(MANIFEST_PATH)
    _validate_manifest(manifest)
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)
    base_notes = build_pattern(str(manifest["pattern"]))
    sources, source_contract = _build_sources(manifest, base_notes)
    results = {
        str(variant["id"]): _evaluate_variant(
            manifest, variant, base_notes, sources[str(variant["id"])]
        )
        for variant in manifest["variants"]
    }
    effects = _factor_effects(results)
    report = {
        "schema_version": 2,
        "experiment_id": manifest["experiment_id"],
        "manifest_sha256": _sha256(MANIFEST_PATH),
        "code_sha256": _code_hashes(),
        "model_version": MODEL_VERSION,
        "onset_tolerance_seconds": ONSET_TOLERANCE_SECONDS,
        "source_contract": source_contract,
        "variants": results,
        "factor_effects": effects,
        "conclusion_codes": _conclusions(effects),
        "conclusion_scope": "synthetic_paired_end_to_end_preprocessing_experiment",
        "model_change_recommended": False,
        "production_change": False,
    }
    report["evaluation_id"] = _payload_hash(report)
    (OUTPUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "experiment_id": report["experiment_id"],
                "evaluation_id": report["evaluation_id"],
                "factor_effects": effects,
                "conclusion_codes": report["conclusion_codes"],
            },
            ensure_ascii=False,
        )
    )
    return report


def _build_sources(
    manifest: dict[str, object], notes: list[SynthNote]
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    sample_rate = int(manifest["sample_rate"])
    duration = float(manifest["duration_seconds"])
    bass_max = int(manifest["bass_pitch_max"])
    unit_bass = _unit_stem(
        [note for note in notes if note.pitch <= bass_max], duration, sample_rate
    )
    unit_treble = _unit_stem(
        [note for note in notes if note.pitch > bass_max], duration, sample_rate
    )
    treble_gain = int(manifest["treble_velocity"]) / 127
    bass_gains = {
        int(variant["bass_velocity"]): int(variant["bass_velocity"]) / 127
        for variant in manifest["variants"]
    }
    pre_gain_mixes = {
        velocity: unit_treble * treble_gain + unit_bass * gain
        for velocity, gain in bass_gains.items()
    }
    shared_gain = 0.82 / max(float(np.max(np.abs(mix))) for mix in pre_gain_mixes.values())
    noise = (
        np.random.default_rng(int(manifest["synthesis_seed"]))
        .normal(
            0,
            float(manifest["noise"]),
            size=unit_treble.shape,
        )
        .astype(np.float32)
    )
    mixed = {velocity: mix * shared_gain + noise for velocity, mix in pre_gain_mixes.items()}
    low, high = (float(value) for value in manifest["device_band_hz"])
    bandwidth_filter = butter(4, [low, high], btype="bandpass", fs=sample_rate, output="sos")
    sources = {}
    for variant in manifest["variants"]:
        source = mixed[int(variant["bass_velocity"])]
        if variant["bandwidth"] == "180-5500":
            source = sosfilt(bandwidth_filter, source)
        sources[str(variant["id"])] = np.clip(source, -1, 1).astype(np.float32)
    shared_root = OUTPUT / "shared"
    shared_root.mkdir()
    shared_files = {
        "unit_bass.wav": unit_bass,
        "unit_treble.wav": unit_treble,
        "noise.wav": noise,
    }
    for name, audio in shared_files.items():
        sf.write(shared_root / name, audio, sample_rate, subtype="FLOAT")
    return sources, {
        "mixing_version": manifest["mixing_version"],
        "noise_injection_stage": manifest["noise_injection_stage"],
        "shared_master_gain": round(shared_gain, 9),
        "shared_files": {name: _sha256(shared_root / name) for name in sorted(shared_files)},
    }


def _unit_stem(notes: list[SynthNote], duration: float, sample_rate: int) -> np.ndarray:
    unit_notes = [SynthNote(note.start, note.end, note.pitch, 127) for note in notes]
    return synthesize(unit_notes, duration, sample_rate, 0.0, False, 0)


def _evaluate_variant(
    manifest: dict[str, object],
    variant: dict[str, object],
    base_notes: list[SynthNote],
    source_audio: np.ndarray,
) -> dict[str, object]:
    variant_root = OUTPUT / str(variant["id"])
    variant_root.mkdir()
    bass_max = int(manifest["bass_pitch_max"])
    notes = [
        SynthNote(
            note.start,
            note.end,
            note.pitch,
            int(variant["bass_velocity"]) if note.pitch <= bass_max else note.velocity,
        )
        for note in base_notes
    ]
    truth_path = variant_root / "truth.mid"
    source_path = variant_root / "source.wav"
    normalized_path = variant_root / "normalized.wav"
    write_midi(notes, truth_path)
    sample_rate = int(manifest["sample_rate"])
    sf.write(source_path, source_audio, sample_rate, subtype="PCM_16")
    preprocess_audio(source_path, normalized_path)
    raw, raw_midi = transcribe_audio(normalized_path)
    harmonic_evidence = extract_harmonic_evidence(normalized_path, raw)
    cleanup = clean_note_events(raw, harmonic_evidence=harmonic_evidence)
    cleaned = cleanup.events
    analysis = analyze_audio(normalized_path)
    scored = build_score(
        cleaned,
        title=str(variant["id"]),
        analysis=analysis,
        harmonic_evidence=harmonic_evidence,
        sustain_evidence=extract_sustain_evidence(normalized_path, raw_midi),
    )
    score_path = variant_root / "score.musicxml"
    write_musicxml(scored, score_path)
    truth = [NoteEvent(n.start, n.end, n.pitch, n.velocity, 1.0) for n in notes]
    raw_events_path = variant_root / "raw-events.json"
    raw_events_path.write_text(
        json.dumps([asdict(event) for event in raw], ensure_ascii=False, indent=2) + "\n"
    )
    raw_layers = _layer_report(raw, truth, bass_max, int(manifest["treble_pitch_min"]))
    cleaned_layers = _layer_report(cleaned, truth, bass_max, int(manifest["treble_pitch_min"]))
    return {
        "factors": {
            "signal_and_noise_bandwidth": variant["bandwidth"],
            "bass_velocity": variant["bass_velocity"],
            "treble_velocity": manifest["treble_velocity"],
            "noise": manifest["noise"],
            "synthesis_seed": manifest["synthesis_seed"],
        },
        "files": {
            "truth_midi_sha256": _sha256(truth_path),
            "source_wav_sha256": _sha256(source_path),
            "normalized_wav_sha256": _sha256(normalized_path),
            "raw_events_sha256": _sha256(raw_events_path),
            "score_musicxml_sha256": _sha256(score_path),
        },
        "spectrum": {
            "source": _spectrum(source_path, bass_max),
            "normalized": _spectrum(normalized_path, bass_max),
        },
        "truth_note_count": len(truth),
        "raw_note_count": len(raw),
        "cleaned_note_count": len(cleaned),
        "raw": raw_layers,
        "cleaned": cleaned_layers,
        "cleanup": cleanup.summary(),
        "cleanup_effect": {
            "bass_recall_delta": round(
                float(cleaned_layers["bass"]["metrics"]["recall"])
                - float(raw_layers["bass"]["metrics"]["recall"]),
                6,
            ),
            "newly_missed_bass_truth_events": _new_misses(raw_layers, cleaned_layers),
        },
        "score_assignment": _score_assignment(scored, truth, bass_max),
    }


def _layer_report(
    estimated: list[NoteEvent],
    truth: list[NoteEvent],
    bass_max: int,
    treble_min: int,
) -> dict[str, object]:
    bands = {
        "all": (estimated, truth),
        "bass": (
            [event for event in estimated if event.pitch <= bass_max],
            [event for event in truth if event.pitch <= bass_max],
        ),
        "treble": (
            [event for event in estimated if event.pitch >= treble_min],
            [event for event in truth if event.pitch >= treble_min],
        ),
    }
    return {
        name: {
            "metrics": evaluate_note_events(candidate, reference),
            "missed_truth_events": [asdict(event) for event in _missed_truth(candidate, reference)],
        }
        for name, (candidate, reference) in bands.items()
    }


def _score_assignment(scored, truth: list[NoteEvent], bass_max: int) -> dict[str, object]:
    bass_truth = [event for event in truth if event.pitch <= bass_max]
    score_events = _score_events(scored, bass_max)
    matched = _match_truth(score_events, bass_truth, tolerance=SCORE_ONSET_TOLERANCE_SECONDS)
    return {
        "reconstruction_status": scored.reconstruction["status"],
        "matching_source": "music21_score_offsets",
        "matching_note": "Quantized onset matching is not raw model recall recovery.",
        "fallback_used": scored.reconstruction["fallback_used"],
        "structure": score_structure_summary(scored.score, validate_measure_durations=True),
        "voicing": scored.reconstruction["voicing"],
        "staff_distribution": scored.reconstruction["staff_distribution"],
        "bass_truth_count": len(bass_truth),
        "matched_bass_truth_count": len(matched),
        "matched_bass_assigned_left_count": sum(
            estimated.hand == "left" for _, estimated in matched
        ),
        "missed_bass_truth_events": [
            asdict(event)
            for event in _missed_truth(
                score_events, bass_truth, tolerance=SCORE_ONSET_TOLERANCE_SECONDS
            )
        ],
    }


def _score_events(scored, bass_max: int) -> list[NoteEvent]:
    quarter_seconds = seconds_per_quarter(scored.analysis)
    events = []
    for part in scored.score.parts:
        hand = "left" if part.id == "left-hand" else "right"
        for item in part.recurse().notes:
            if item.tie is not None and item.tie.type in {"continue", "stop"}:
                continue
            pitches = item.pitches if item.isChord else (item.pitch,)
            start = float(item.getOffsetInHierarchy(scored.score)) * quarter_seconds
            end = start + float(item.quarterLength) * quarter_seconds
            for value in pitches:
                if value.midi <= bass_max:
                    events.append(NoteEvent(start, end, value.midi, 100, 1.0, hand=hand))
    return events


def _new_misses(
    raw_layers: dict[str, object], cleaned_layers: dict[str, object]
) -> list[dict[str, object]]:
    raw = {(item["start_sec"], item["pitch"]) for item in raw_layers["bass"]["missed_truth_events"]}
    return [
        item
        for item in cleaned_layers["bass"]["missed_truth_events"]
        if (item["start_sec"], item["pitch"]) not in raw
    ]


def _spectrum(path: Path, bass_max: int) -> dict[str, object]:
    audio, sample_rate = sf.read(path, dtype="float32")
    frequencies, power = welch(audio, fs=sample_rate, nperseg=8192)

    def band_rms(low: float, high: float) -> float:
        mask = (frequencies >= low) & (frequencies <= high)
        return float(np.sqrt(np.trapz(power[mask], frequencies[mask])))

    low_rms = band_rms(40, 180)
    treble_rms = band_rms(700, 5000)
    fundamentals = {}
    for pitch in (36, 41, 43):
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        fundamentals[str(pitch)] = {
            "frequency_hz": round(frequency, 3),
            "rms": round(band_rms(frequency - 4, frequency + 4), 9),
            "below_bass_cutoff": frequency < 180 and pitch <= bass_max,
        }
    return {
        "total_rms": round(float(np.sqrt(np.mean(audio**2))), 9),
        "low_40_180_rms": round(low_rms, 9),
        "treble_700_5000_rms": round(treble_rms, 9),
        "low_to_treble_rms_ratio": round(low_rms / max(treble_rms, 1e-12), 9),
        "bass_fundamentals": fundamentals,
    }


def _missed_truth(
    estimated: list[NoteEvent],
    truth: list[NoteEvent],
    *,
    tolerance: float = ONSET_TOLERANCE_SECONDS,
) -> list[NoteEvent]:
    matched = _match_truth(estimated, truth, tolerance=tolerance)
    matched_truth = {id(reference) for reference, _ in matched}
    return [event for event in truth if id(event) not in matched_truth]


def _match_truth(
    estimated: list[NoteEvent],
    truth: list[NoteEvent],
    *,
    tolerance: float = ONSET_TOLERANCE_SECONDS,
) -> list[tuple[NoteEvent, NoteEvent]]:
    unused = set(range(len(estimated)))
    matched = []
    for reference in sorted(truth, key=_event_key):
        candidates = [
            index
            for index in unused
            if estimated[index].pitch == reference.pitch
            and abs(estimated[index].start_sec - reference.start_sec) <= tolerance
        ]
        if not candidates:
            continue
        winner = min(
            candidates,
            key=lambda index: abs(estimated[index].start_sec - reference.start_sec),
        )
        unused.remove(winner)
        matched.append((reference, estimated[winner]))
    return matched


def _factor_effects(results: dict[str, dict[str, object]]) -> dict[str, float]:
    recall = {
        name: float(result["raw"]["bass"]["metrics"]["recall"]) for name, result in results.items()
    }
    weak_full = recall["full-weak"] - recall["full-standard"]
    weak_device = recall["device-weak"] - recall["device-standard"]
    return {
        "bandwidth_at_standard_velocity": round(
            recall["device-standard"] - recall["full-standard"], 6
        ),
        "bandwidth_at_weak_velocity": round(recall["device-weak"] - recall["full-weak"], 6),
        "weak_velocity_at_full_bandwidth": round(weak_full, 6),
        "weak_velocity_at_device_bandwidth": round(weak_device, 6),
        "bandwidth_velocity_interaction": round(weak_device - weak_full, 6),
    }


def _conclusions(effects: dict[str, float]) -> list[str]:
    conclusions = []
    if effects["bandwidth_at_standard_velocity"] < 0 and effects["bandwidth_at_weak_velocity"] < 0:
        conclusions.append("BANDWIDTH_REDUCES_BASS_RECALL_IN_BOTH_VELOCITY_CONDITIONS")
    if effects["weak_velocity_at_full_bandwidth"] < 0:
        conclusions.append("WEAK_BASS_REDUCES_RECALL_AT_FULL_BANDWIDTH")
    if effects["bandwidth_velocity_interaction"] < 0:
        conclusions.append("BANDLIMITED_WEAK_BASS_INTERACTION")
    return conclusions or ["NO_FACTOR_EFFECT_DETECTED"]


def _validate_manifest(manifest: dict[str, object]) -> None:
    factors = {(variant["bandwidth"], variant["bass_velocity"]) for variant in manifest["variants"]}
    if factors != {
        ("full", 78),
        ("180-5500", 78),
        ("full", 38),
        ("180-5500", 38),
    }:
        raise ValueError("device bass experiment must remain a complete 2x2 design")
    if manifest.get("noise_injection_stage") != "before_bandwidth_filter":
        raise ValueError("noise must be part of the paired bandwidth input")
    if manifest.get("production_change") is not False:
        raise ValueError("device bass experiment cannot enable production changes")


def _code_hashes() -> dict[str, str]:
    paths = [
        *(ROOT / "app/pipeline" / name for name in PIPELINE_FILES),
        ROOT / "app/pipeline/quality.py",
        ROOT / "scripts/generate_regression_set.py",
        Path(__file__),
    ]
    return {str(path.relative_to(ROOT)): _sha256(path) for path in sorted(set(paths))}


def _event_key(event: NoteEvent) -> tuple[float, int, float]:
    return event.start_sec, event.pitch, event.end_sec


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


if __name__ == "__main__":
    evaluate()
