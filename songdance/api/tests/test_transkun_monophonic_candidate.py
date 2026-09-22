import json

from scripts.piano_comparison_cases import BATCH_ROOT


def test_soft_candidate_is_single_treble_staff_after_onset_duration_rebuild():
    data = json.loads((BATCH_ROOT / "07-soft/transkun-v2/monophonic-validation.json").read_text())
    s = data["structure"]
    assert data["event_count"] == 40
    assert s["staff_count"] == 1
    assert s["voice_count"] == 0
    assert s["rest_count"] == 0
    assert s["measure_duration_error_count"] == 0


def test_device_is_not_classified_as_monophonic():
    rows = json.loads((BATCH_ROOT / "monophonic-diagnostic.json").read_text())
    device = next(row for row in rows if row["case_id"] == "10-device")
    assert device["monophonic_candidate"] is False
    assert device["simultaneous_clusters"] > 0
    assert device["low_register_events"] > 0
