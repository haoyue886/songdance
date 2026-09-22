import json

import pytest

from scripts.audit_soundfont_octaves import audit
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT


def event(pitch):
    return {"pitch": pitch, "start_sec": 1.0, "end_sec": 1.5, "velocity": 80}


def test_real_octave_counterexample_rejects_deletion():
    notes = [event(48), event(60)]
    report = {"case_id": "real-octave", "variant": "control", "events": notes}
    result = audit(report, notes)
    assert result["matched_count_loss"] == 1
    assert result["rule_status"] == "rejected_false_deletion"
    assert report["events"] == notes


def test_false_octave_is_measured_but_does_not_authorize_rule():
    result = audit(
        {"case_id": "false-octave", "variant": "control", "events": [event(48), event(60)]},
        [event(48)],
    )
    assert result["extra_count_reduction"] == 1
    assert result["matched_count_loss"] == 0
    assert result["rule_status"] == "not_validated_for_production"


@pytest.mark.parametrize("case", ("06-sustain", "07-soft", "14-hand-crossing"))
@pytest.mark.parametrize("variant", ("original", "soundfont"))
def test_actual_audit_counts_recompute(case, variant):
    root = BATCH_ROOT / "soundfont-cross-cases-v1"
    result = json.loads((root / "octave-rule-audit.json").read_text())
    expected = next(r for r in result["trials"] if r["case_id"] == case and r["variant"] == variant)
    report = json.loads((root / case / variant / "evaluation.json").read_text())
    notes = read_midi(ROOT / f"tests/fixtures/audio/generated/{case}.mid")
    reference = list({(n["start_sec"], n["pitch"]): n for n in notes}.values())
    recalculated = audit(report, reference)
    assert all(expected[key] == value for key, value in recalculated.items())
    assert result["actual_deleted_notes"] == 0
