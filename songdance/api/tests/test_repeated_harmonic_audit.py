import json

import pytest

from app.pipeline.harmonics import HarmonicEvidence, extract_harmonic_evidence
from app.pipeline.transcribe import NoteEvent
from scripts.audit_repeated_harmonics import selected_indices
from scripts.piano_comparison_cases import ROOT, file_sha256

OUTPUT = ROOT / "tests/fixtures/audio/candidates/15-harmonic-audit-v1"


def test_missing_evidence_never_silently_means_safe_deletion():
    with pytest.raises(ValueError, match="unavailable"):
        selected_indices([NoteEvent(0, 1, 60, 80, 0.5)], HarmonicEvidence.unavailable())


def test_full_audit_preserves_original_and_rejects_unsafe_policy():
    report = json.loads((OUTPUT / "audit.json").read_text())
    raw = ROOT / "tests/fixtures/audio/structure-review-artifacts/15-repeated-notes/raw.mid"
    assert report["raw_sha256"] == file_sha256(raw)
    assert report["actual_applied_deletions"] == 0
    assert report["hypothetical_deleted_indices"] == []
    assert report["before"] == report["after"]
    assert report["after"]["matched_count"] == 118
    assert report["after"]["extra_count"] == 119
    assert report["control_real_note_deletions"] == 3
    assert report["conclusion"] == "unsafe_on_controls"
    assert report["code_sha256"]["scripts/audit_repeated_harmonics.py"] == file_sha256(
        OUTPUT / "executed-script.py"
    )


def test_all_control_decisions_recompute_from_audio_not_report_labels():
    report = json.loads((OUTPUT / "audit.json").read_text())
    false_deletions = 0
    for control in report["controls"]:
        path = OUTPUT / control["id"]
        assert file_sha256(path) == control["sha256"]
        events = [NoteEvent(**n) for n in control["events"]]
        evidence = extract_harmonic_evidence(path, events)
        selected = selected_indices(events, evidence)
        assert selected == control["selected"]
        false_deletions += len(set(selected) & set(control["real_indices"]))
    assert false_deletions == 3
