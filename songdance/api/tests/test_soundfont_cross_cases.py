import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from scripts import run_soundfont_cross_cases as batch
from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.evaluate_device_context_shift import restore
from scripts.piano_comparison_cases import BATCH_ROOT, ROOT, file_sha256


@pytest.mark.parametrize("case", batch.CASES)
@pytest.mark.parametrize("variant", ("original", "soundfont"))
def test_actual_paired_trial_recomputes_and_preserves_padding(case, variant):
    folder = BATCH_ROOT / "soundfont-cross-cases-v1" / case / variant
    report = json.loads((folder / "evaluation.json").read_text())
    assert report["case_id"] == case and report["variant"] == variant
    assert report["production_eligible"] is False
    assert json.loads((folder / "status.json").read_text())["status"] == "complete"
    for name, digest in report["artifacts"].items():
        assert file_sha256(folder / name) == digest
    y, rate = sf.read(folder / "normalized.wav", dtype="int16")
    z, other = sf.read(folder / "padded.wav", dtype="int16")
    assert rate == other == 22050 and np.array_equal(y, z[rate:-rate])
    receipt = json.loads((folder / "transkun/inference.json").read_text())
    assert receipt["midi_sha256"] == file_sha256(folder / "transkun/raw.mid")
    assert receipt["input_sha256"] == file_sha256(folder / "padded.wav")
    assert report["receipt_sha256"] == file_sha256(folder / "transkun/inference.json")
    notes, clipped, rejected = restore(read_midi(folder / "transkun/raw.mid"), 1, 30)
    assert (
        report["events"] == notes
        and report["clipped"] == clipped
        and report["rejected"] == rejected
    )
    ref_path = ROOT / f"tests/fixtures/audio/generated/{case}.mid"
    assert report["reference_sha256"] == file_sha256(ref_path)
    original = read_midi(ref_path)
    reference = list({(n["start_sec"], n["pitch"]): n for n in original}.values())
    assert len(original) == report["source_midi_count"]
    assert len(reference) == report["distinct_reference_count"]
    assert report["metrics"] == {str(t): note_metrics(reference, notes, t) for t in (0.05, 0.1)}


def test_failed_batch_stops_and_preserves_failure_record(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(batch.subprocess, "run", fail)
    destination = tmp_path / "new"
    with pytest.raises(RuntimeError, match="controlled"):
        batch.run(Path("/unused"), Path("/unused"), destination)
    receipt = destination / "06-sustain/original/status.json"
    assert json.loads(receipt.read_text())["status"] == "failed"
    assert not (destination / "summary.json").exists()
    with pytest.raises(FileExistsError):
        batch.run(Path("/unused"), Path("/unused"), destination)
