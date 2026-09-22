import json
import subprocess
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from scripts import run_transkun_candidate as entry
from scripts.piano_comparison_cases import ROOT, file_sha256


def fake_environment(tmp_path, monkeypatch, mode="success"):
    source = tmp_path / "source.wav"
    sf.write(source, np.zeros(22050), 22050)

    def preprocess(src, dst):
        dst.write_bytes(src.read_bytes())

    monkeypatch.setattr(entry, "preprocess_audio", preprocess)

    def infer(command, **kwargs):
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        folder = Path(command[command.index("--output") + 1])
        audio = Path(command[command.index("--audio") + 1])
        folder.mkdir()
        midi = pretty_midi.PrettyMIDI()
        piano = pretty_midi.Instrument(0)
        piano.notes = [pretty_midi.Note(70, 60, 0.1, 0.6)]
        midi.instruments.append(piano)
        midi.write(str(folder / "raw.mid"))
        receipt = {
            "status": "inference_complete",
            "model": "test-model",
            "raw_note_count": 1,
            "input_sha256": file_sha256(audio),
            "manifest_sha256": file_sha256(entry.MANIFEST),
            "adapter_sha256": file_sha256(entry.RUNNER),
            "midi_sha256": file_sha256(folder / "raw.mid"),
        }
        if mode == "wrong_input":
            audio.write_bytes(b"changed")
        if mode == "count":
            receipt["raw_note_count"] = 9
        (folder / "inference.json").write_text(json.dumps(receipt))

    monkeypatch.setattr(entry.subprocess, "run", infer)
    return source


def test_success_keeps_raw_times_unknown_confidence_and_rejects_overwrite(tmp_path, monkeypatch):
    source = fake_environment(tmp_path, monkeypatch)
    output = tmp_path / "output"
    result = entry.run(source, output, Path("/unused/python"), Path("/unused/source"))
    assert result["status"] == "complete" and result["production_eligible"] is False
    timeline = json.loads((output / "raw-timeline.json").read_text())
    assert timeline["notes"] == entry.read_events(output / "model/raw.mid")
    assert timeline["notes"][0]["confidence"] is None
    assert timeline["notes"][0]["hand"] is None
    for name, digest in result["artifacts_sha256"].items():
        assert file_sha256(output / name) == digest
    with pytest.raises(FileExistsError):
        entry.run(source, output, Path("/unused"), Path("/unused"))


@pytest.mark.parametrize("mode", ("timeout", "wrong_input", "count"))
def test_failed_inference_or_verification_never_exports_success(tmp_path, monkeypatch, mode):
    source = fake_environment(tmp_path, monkeypatch, mode)
    output = tmp_path / "output"
    with pytest.raises((subprocess.TimeoutExpired, ValueError)):
        entry.run(source, output, Path("/unused/python"), Path("/unused/source"), timeout=0.1)
    receipt = json.loads((output / "pipeline.json").read_text())
    assert receipt["status"] == "failed" and receipt["production_eligible"] is False
    assert not (output / "raw-timeline.json").exists()


def test_actual_isolated_inference_exports_identical_raw_midi_events():
    output = ROOT / "tests/fixtures/audio/candidates/transkun-entry-smoke-07-v2"
    receipt = json.loads((output / "pipeline.json").read_text())
    timeline = json.loads((output / "raw-timeline.json").read_text())
    assert receipt["status"] == "complete"
    assert receipt["raw_note_count"] == len(timeline["notes"]) == 40
    assert timeline["notes"] == entry.read_events(output / "model/raw.mid")
    for name, digest in receipt["artifacts_sha256"].items():
        assert file_sha256(output / name) == digest
    assert all(n["confidence"] is None and n["hand"] is None for n in timeline["notes"])


def test_virtualenv_interpreter_symlink_is_not_resolved(tmp_path, monkeypatch):
    source = fake_environment(tmp_path, monkeypatch)
    target = tmp_path / "real-python"
    target.write_text("placeholder")
    interpreter = tmp_path / "venv-python"
    interpreter.symlink_to(target)
    infer = entry.subprocess.run

    def check(command, **kwargs):
        assert command[0] == str(interpreter.absolute())
        return infer(command, **kwargs)

    monkeypatch.setattr(entry.subprocess, "run", check)
    entry.run(source, tmp_path / "output", interpreter, tmp_path)
