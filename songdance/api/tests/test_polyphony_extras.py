from dataclasses import replace

import pytest

from app.pipeline.harmonics import HarmonicEvidence
from scripts.audit_polyphony_extras import annotate, evaluate, run


def test_unavailable_evidence_cannot_select():
    with pytest.raises(ValueError, match="unavailable"):
        evaluate([], HarmonicEvidence.unavailable())


def test_source_labels_cannot_change_selected_indices():
    raw = [{"pitch": 60, "start_sec": 0.5, "end_sec": 0.7, "velocity": 80}]
    reference = [{"pitch": 60, "start_sec": 0, "end_sec": 1, "velocity": 80}]
    evidence = replace(HarmonicEvidence.unavailable(), status="available")
    selected = {"harmonic": [0], "tail": []}
    _, rows, decisions = annotate(raw, reference, evidence, selected)
    assert rows[0]["source_same_pitch_sounding_indices"] == [0]
    assert decisions["harmonic"]["unmatched_onsets_selected"] == 1
    _, _, changed = annotate(raw, raw, evidence, selected)
    assert changed["harmonic"]["matched_onsets_selected"] == 1
    assert selected == {"harmonic": [0], "tail": []}


def test_real_audio_audit_is_read_only_and_refuses_overwrite(tmp_path):
    output = tmp_path / "audit"
    report = run(output)
    assert report["source_reconstruction"]["pcm_samples_equal"]
    assert report["label_counts"] == {"matched_onset": 120, "unmatched_onset": 29}
    assert len(report["events"]) == 149
    assert report["actual_applied_deletions"] == 0
    assert not report["production_eligible"]
    assert not list(output.glob("*.mid"))
    for d in report["decisions"].values():
        assert d["selected"] == d["matched_onsets_selected"] + d["unmatched_onsets_selected"]
    before = (output / "audit.json").read_bytes()
    with pytest.raises(FileExistsError):
        run(output)
    assert (output / "audit.json").read_bytes() == before


def test_unavailable_audio_leaves_failed_audit(tmp_path, monkeypatch):
    import json

    from scripts import audit_polyphony_extras as audit

    monkeypatch.setattr(
        audit, "extract_harmonic_evidence", lambda *args, **kwargs: HarmonicEvidence.unavailable()
    )
    output = tmp_path / "failed"
    with pytest.raises(ValueError, match="unavailable"):
        audit.run(output)
    assert json.loads((output / "status.json").read_text())["status"] == "failed"
    assert not (output / "audit.json").exists()
