import json

import pytest

from scripts import prepare_sustain_review_source as source
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import file_sha256


def test_prepared_source_is_three_notes_per_attack_and_cannot_overwrite(tmp_path):
    output = tmp_path / "new-source"
    receipt = source.prepare(output)
    notes = read_midi(output / "reference.mid")
    assert len(notes) == 45
    times = sorted({n["start_sec"] for n in notes})
    assert times == list(range(0, 30, 2))
    for i, t in enumerate(times):
        assert sorted(n["pitch"] for n in notes if n["start_sec"] == t) == source.EXPECTED[i % 3]
    for name, digest in receipt["artifacts"].items():
        assert file_sha256(output / name) == digest
    assert receipt["production_eligible"] is False
    assert receipt["status"] == "source_prepared_not_transcribed"
    with pytest.raises(FileExistsError):
        source.prepare(output)


def test_audio_failure_keeps_failed_receipt(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError("controlled failure")

    monkeypatch.setattr(source, "synthesize", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        source.prepare(tmp_path / "source")
    receipt = json.loads((tmp_path / "source/source-receipt.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["production_eligible"] is False
