"""Re-encode a reviewed meter hypothesis without fabricating or deleting model notes."""

import argparse
import copy
import json
from pathlib import Path

import pretty_midi

from scripts.audit_teacher_reviews_15_16 import CONTRACT, FIXTURES, verify_inputs
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import file_sha256

QUARTER_BPM = 60
MEASURE_SECONDS = 2.0
RESOLUTION = 9600
MAX_TICK_ERROR_SECONDS = 1 / RESOLUTION + 1e-9


def verify_roundtrip(before, after):
    """Reject importer note-pairing changes rather than calling them tempo conversion."""
    if len(before) != len(after):
        raise ValueError("meter encoding changed event count")
    maximum_error = 0.0
    for source, result in zip(before, after, strict=True):
        if (source["pitch"], source["velocity"]) != (result["pitch"], result["velocity"]):
            raise ValueError("meter encoding changed pitch or velocity")
        for key in ("start_sec", "end_sec"):
            error = abs(source[key] - result[key])
            if error > MAX_TICK_ERROR_SECONDS:
                raise ValueError("meter encoding changed absolute timing")
            maximum_error = max(maximum_error, error)
    return maximum_error


def beat_position(start_seconds):
    measure = int(start_seconds // MEASURE_SECONDS)
    nearest = round(start_seconds / MEASURE_SECONDS) * MEASURE_SECONDS
    return {
        "measure_index": measure,
        "quarter_offset": start_seconds % MEASURE_SECONDS,
        "nearest_downbeat_seconds": nearest,
        "distance_from_nearest_downbeat_seconds": start_seconds - nearest,
    }


def run(output: Path):
    if output.exists():
        raise ValueError("output exists; do not overwrite a prior candidate")
    contract = json.loads(CONTRACT.read_text())
    bindings = verify_inputs(FIXTURES, contract)["16-noisy-polyphony"]
    original_path = bindings["original/raw.mid"]
    original = pretty_midi.PrettyMIDI(str(original_path))
    before = read_midi(original_path)
    output.mkdir(parents=True, exist_ok=False)
    state = {
        "production_eligible": False,
        "status": "running",
        "feedback_sha256": file_sha256(CONTRACT),
        "source_audio_sha256": file_sha256(bindings["source_wav"]),
        "original_midi_sha256": file_sha256(original_path),
        "script_sha256": file_sha256(Path(__file__)),
    }
    try:
        converted = pretty_midi.PrettyMIDI(initial_tempo=QUARTER_BPM, resolution=RESOLUTION)
        converted.instruments = copy.deepcopy(original.instruments)
        converted.key_signature_changes = copy.deepcopy(original.key_signature_changes)
        converted.lyrics = copy.deepcopy(original.lyrics)
        converted.text_events = copy.deepcopy(original.text_events)
        converted.time_signature_changes = [pretty_midi.TimeSignature(2, 4, 0)]
        destination = output / "candidate.mid"
        converted.write(str(destination))
        after = read_midi(destination)
        max_error = verify_roundtrip(before, after)
        # Reference is consulted only after export and integrity verification.
        reference = read_midi(bindings["source_midi"])
        comparisons = {
            str(t): {
                "before": note_metrics(reference, before, t),
                "after": note_metrics(reference, after, t),
            }
            for t in (0.05, 0.1)
        }
        state.update(
            status="meter_only_candidate_source_conflict_unresolved",
            meter="2/4",
            quarter_bpm=QUARTER_BPM,
            configuration_source="teacher_meter_and_existing_audio_group_interval",
            bar_origin_seconds=0,
            bar_origin_source="presentation_assumption_not_detected",
            measure_seconds=MEASURE_SECONDS,
            raw_event_count=len(before),
            candidate_event_count=len(after),
            actual_note_additions=0,
            actual_note_deletions=0,
            applied_quantization=False,
            hand_assignment="not_applied",
            maximum_roundtrip_time_error_seconds=max_error,
            midi_sha256=file_sha256(destination),
            reference_sha256=file_sha256(bindings["source_midi"]),
            events=[
                {"before": n, "after": m, "position": beat_position(m["start_sec"])}
                for n, m in zip(before, after, strict=True)
            ],
            metrics_onsets_only=comparisons,
            unresolved=[
                "four_note_source_vs_teacher_triad",
                "extra_model_events",
                "note_durations_and_hands",
                "audio_verified_downbeat_alignment",
            ],
        )
    except Exception as error:
        state.update(status="failed", error=str(error))
        raise
    finally:
        (output / "audit.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    print(state["status"], state["candidate_event_count"], max_error)
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args().output)
