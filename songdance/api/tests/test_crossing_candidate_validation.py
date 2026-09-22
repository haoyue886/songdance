import json

import pretty_midi
import pytest

from app.pipeline.artifacts import artifact_paths, write_timeline
from app.pipeline.cleanup import clean_note_events
from app.pipeline.score import build_score, write_musicxml, write_quantized_midi
from app.pipeline.transcribe import NoteEvent
from scripts.build_crossing_eighth_candidate import (
    OUTPUT_DIR,
    SOURCE_MIDI,
    SOURCE_WAV,
    code_hashes,
    file_sha256,
)
from scripts.crossing_candidate_validation import validate_saved_outputs
from scripts.run_structure_review import _notation_context_for_case


def _write_candidate(root):
    context = _notation_context_for_case({"texture_hint": "crossing_eighth_melody"})
    events = [
        NoteEvent(i * 0.5, i * 0.5 + length, p, 88, 0.9)
        for i in range(8)
        for p, length in ((48 + i * 3, 0.65), (72 - i * 3, 0.42))
    ]
    cleaned = clean_note_events(events, preserve_simultaneous_unisons=True)
    assert len(cleaned.events) == len(events)
    scored = build_score(cleaned.events, notation_context=context)
    paths = artifact_paths(root)
    write_musicxml(scored, paths["musicxml"])
    write_quantized_midi(scored, paths["midi"])
    write_timeline(scored, paths["timeline"])
    return paths


def test_saved_output_gate_checks_unison_multiplicity_and_actual_notated_duration(tmp_path):
    result = validate_saved_outputs(_write_candidate(tmp_path))
    assert result["status"] == "passed"
    assert result["xml_note_value_quarters"] == [0.5]
    assert result["xml_pitch_event_count"] == result["midi_pitch_event_count"] == 16


def test_unison_preservation_is_opt_in_and_records_its_policy():
    events = [NoteEvent(2.0, 2.42, 60, 88, 0.9), NoteEvent(2.0, 2.65, 60, 78, 0.8)]
    default = clean_note_events(events)
    crossing = clean_note_events(events, preserve_simultaneous_unisons=True)
    assert len(default.events) == 1
    assert len(crossing.events) == 2
    assert crossing.summary()["simultaneous_unison_policy"] == "preserve"
    assert crossing.summary()["version"] != default.summary()["version"]


def test_tail_cleanup_requires_root_attack_decay_and_other_attack():
    from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
    from app.pipeline.harmonics import HarmonicEvidence, NoteOnsetEvidence

    events = [
        NoteEvent(0.0, 0.49, 48, 80, 0.8),
        NoteEvent(0.5, 0.99, 48, 40, 0.4),
        NoteEvent(0.5, 0.99, 72, 80, 0.8),
    ]
    evidence = HarmonicEvidence(
        version="test",
        status="available",
        source="AUDIO_STFT",
        removals=(),
        onset_observations=(
            NoteOnsetEvidence(48, 0.0, 0.49, 3.0, True),
            NoteOnsetEvidence(48, 0.5, 0.99, 0.5, False, 0.2, 0.1, 0.01, 0.01),
            NoteOnsetEvidence(72, 0.5, 0.99, 3.0, True),
        ),
    )
    kept, audit = clean_crossing_tails(events, evidence, 0.5)
    assert [(e.start_sec, e.pitch) for e in kept] == [(0.0, 48), (0.5, 72)]
    assert audit["removed_count"] == 1
    assert audit["removals"][0]["root_event"]["pitch"] == 48


@pytest.mark.parametrize("mutation", ["duration", "tempo", "missing_note"])
def test_gate_rejects_wrong_midi_even_when_in_memory_timeline_is_green(tmp_path, mutation):
    paths = _write_candidate(tmp_path)
    midi = pretty_midi.PrettyMIDI(str(paths["midi"]))
    if mutation == "duration":
        midi.instruments[0].notes[0].end += 0.5
    elif mutation == "missing_note":
        midi.instruments[0].notes.pop()
    else:
        other = pretty_midi.PrettyMIDI(initial_tempo=120)
        other.instruments = midi.instruments
        other.time_signature_changes = midi.time_signature_changes
        midi = other
    midi.write(str(paths["midi"]))
    result = validate_saved_outputs(paths)
    assert result["status"] == "failed"
    assert not result["checks"][
        "quarter_tempo_60" if mutation == "tempo" else "midi_matches_timeline"
    ]


def test_real_wav_candidate_preserves_sources_and_reports_pitch_limitations():
    report = json.loads((OUTPUT_DIR / "candidate-report.json").read_text())
    assert report["source_sha256"] == file_sha256(SOURCE_WAV)
    assert report["source_midi_sha256"] == file_sha256(SOURCE_MIDI)
    assert report["code_sha256"] == code_hashes()
    for name, sha in report["artifacts_sha256"].items():
        assert file_sha256(OUTPUT_DIR / "artifacts" / name) == sha
    result = validate_saved_outputs(artifact_paths(OUTPUT_DIR / "artifacts"))
    assert result == report["saved_output_validation"]
    assert result["status"] == "passed"
    assert all(p["status"] == "passed" for p in report["parser_validation"].values())
    # The model adds an unconfirmed last onset. Preserve it instead of filling/deleting by truth.
    assert result["onset_group_count"] == 60
    assert result["last_notated_end_seconds"] == 30.0
    assert report["status"] == "candidate_needs_review"
    assert report["human_rating"] == "pending"
    assert report["production_eligible"] is False
    assert report["reference"]["onset_group_count"] == 59
    assert report["reference"]["distinct_pitch_onsets"] == 111
    assert report["reference"]["missing_reference_events"] == 0
    assert report["reference"]["unmatched_output_events"] > 0
    assert report["raw_note_count"] == 285
    removed_count = report["crossing_tail_cleanup"]["removed_count"]
    assert removed_count > 0
    assert report["notation_note_count"] == 264 - removed_count
    assert report["reference"]["unmatched_output_events"] == 153 - removed_count
    assert report["tail_evaluation"]["correct_onsets_preserved"] is True
    assert report["tail_evaluation"]["extra_event_reduction"] == removed_count
    assert report["tail_evaluation"]["baseline_notation_count"] == 264
    assert "app/pipeline/crossing_tail_cleanup.py" in report["code_sha256"]
    timeline = json.loads((OUTPUT_DIR / "artifacts/timeline.json").read_text())
    assert timeline["reconstruction"]["crossing_tail_cleanup"] == report["crossing_tail_cleanup"]


def test_real_tail_removal_audit_never_removes_a_reference_attack_or_a_root():
    report = json.loads((OUTPUT_DIR / "candidate-report.json").read_text())
    raw = json.loads((OUTPUT_DIR / "raw-events.json").read_text())
    source = pretty_midi.PrettyMIDI(str(SOURCE_MIDI))
    truth = {(round(n.start / .5), n.pitch) for i in source.instruments for n in i.notes}
    audit = report["crossing_tail_cleanup"]
    assert audit["removed_count"] == len(audit["removals"]) > 0
    removed = [r["event"] for r in audit["removals"]]
    for removal in audit["removals"]:
        e = removal["event"]
        assert e in raw
        assert (round(e["start_sec"] / .5), e["pitch"]) not in truth
        assert removal["root_event"] in raw and removal["root_event"] not in removed
        assert removal["direct_predecessor"] in raw
        assert removal["other_independent_attacks"]
        assert all(a["event"] in raw and a["event"] not in removed
                   for a in removal["other_independent_attacks"])
        assert e["start_sec"] - removal["root_event"]["start_sec"] <= 1.08
        assert 0 <= removal["onset_evidence"]["transient_fit_error"] <= .01
        assert abs(removal["onset_evidence"]["transient_reference_sec"] - e["start_sec"]) <= .08
