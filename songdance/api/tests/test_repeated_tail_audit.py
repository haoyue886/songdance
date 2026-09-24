import json
from dataclasses import asdict

from app.pipeline.crossing_tail_cleanup import clean_crossing_tails
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def test_actual_repeated_tail_audit_recomputes_and_never_claims_quality_fix():
    fixtures = ROOT / "tests/fixtures/audio"
    folder = fixtures / "candidates/15-tail-audit-v1"
    report = json.loads((folder / "audit.json").read_text())
    raw = read_midi(fixtures / "structure-review-artifacts/15-repeated-notes/raw.mid")
    events = [
        NoteEvent(n["start_sec"], n["end_sec"], n["pitch"], n["velocity"], n["velocity"] / 127)
        for n in raw
    ]
    assert report["normalized_sha256"] == file_sha256(folder / "normalized.wav")
    for name, digest in report["code"].items():
        assert file_sha256(ROOT / name) == digest
    evidence = extract_harmonic_evidence(
        folder / "normalized.wav",
        events,
        include_decay_evidence=True,
        include_transient_evidence=True,
    )
    kept, decisions = clean_crossing_tails(events, evidence, 0.5)
    assert decisions == report["decisions"]
    assert decisions["removed_count"] == 0 and kept == events
    reference = read_midi(fixtures / "generated/15-repeated-notes.mid")
    assert report["before"] == note_metrics(reference, raw, 0.1)
    assert report["after_hypothetical"] == note_metrics(reference, [asdict(n) for n in kept], 0.1)
    for key in ("matched_count", "extra_count", "missing_count"):
        assert report["after_hypothetical"][key] == report["before"][key]
    assert report["before"]["matched_count"] == 118
    assert report["before"]["extra_count"] == 119
    assert report["actual_applied_deletions"] == 0
    assert report["production_eligible"] is False
