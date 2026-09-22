import json

import pytest

from scripts import compare_cross_case_models as batch
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


@pytest.mark.parametrize("case", batch.CASES)
@pytest.mark.parametrize("variant", ("original", "soundfont"))
def test_two_models_have_same_input_and_full_metrics_recompute(case, variant):
    dest = BATCH_ROOT / "cross-case-model-comparison-v1" / case / variant
    source = BATCH_ROOT / "soundfont-cross-cases-v1" / case / variant
    report = json.loads((dest / "comparison.json").read_text())
    receipt = json.loads((source / "transkun/inference.json").read_text())
    assert report["input_sha256"] == receipt["input_sha256"] == file_sha256(source / "padded.wav")
    assert report["raw_midi_sha256"] == file_sha256(dest / "raw.mid")
    assert report["raw_events_sha256"] == file_sha256(dest / "raw-events.json")
    assert report["transkun_receipt_sha256"] == file_sha256(source / "transkun/inference.json")
    ref_path = ROOT / f"tests/fixtures/audio/generated/{case}.mid"
    assert report["reference_sha256"] == file_sha256(ref_path)
    source_notes = read_midi(ref_path)
    reference = list({(n["start_sec"], n["pitch"]): n for n in source_notes}.values())
    for model, events in [
        ("basic", json.loads((dest / "raw-events.json").read_text())),
        ("transkun", read_midi(source / "transkun/raw.mid")),
    ]:
        restored, _, _ = restore(events, 1, 30)
        assert report[model] == {str(t): note_metrics(reference, restored, t) for t in (0.05, 0.1)}
    assert report["production_eligible"] is False


def test_model_failure_is_recorded_without_overwriting(tmp_path, monkeypatch):
    # Keep read-only source fixtures available through symlink; isolate all new output.
    (tmp_path / "soundfont-cross-cases-v1").symlink_to(BATCH_ROOT / "soundfont-cross-cases-v1")
    monkeypatch.setattr(batch, "BATCH_ROOT", tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(batch, "transcribe_audio", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        batch.run()
    output = tmp_path / "cross-case-model-comparison-v1"
    assert (
        json.loads((output / "06-sustain/original/status.json").read_text())["status"] == "failed"
    )
    assert not (output / "summary.json").exists()
    with pytest.raises(FileExistsError):
        batch.run()
