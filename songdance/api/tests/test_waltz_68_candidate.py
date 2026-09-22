import json
from pathlib import Path

from scripts.generate_regression_set import build_pattern


def test_waltz_68_candidate_contract_is_not_the_legacy_three_four_case():
    root = Path(__file__).parent / "fixtures/audio"
    manifest = json.loads((root / "waltz-68-reference-manifest.json").read_text())
    assert manifest["status"] in {
        "teacher_sequence_recorded_pending_octave_check",
        "technical_candidate_rejected_pending_pitch_alignment",
    }
    assert manifest["case"]["time_signature"] == "6/8"
    assert manifest["case"]["bass_note_value"] == "dotted_quarter"
    assert manifest["case"]["treble_note_value"] == "eighth"
    assert build_pattern("waltz_68_reference") != build_pattern("waltz_34")
