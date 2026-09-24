import json
import shutil

import pytest

from scripts.piano_comparison_cases import BATCH_ROOT, file_sha256
from scripts.run_real_partial_probe import CASE, run, verify


def test_real_recording_coverage_has_no_accuracy_claim(tmp_path):
    out = tmp_path / "run"
    report = run(out)
    assert report["event_count"] == 242
    assert sum(report["event_status_counts"].values()) == 242
    assert report["accuracy"] is None
    assert report["false_deletion_rate"] is None
    assert report["reference_note_labels"] is None
    assert report["actual_applied_deletions"] == 0
    assert report["production_eligible"] is False
    assert not list(out.glob("*.mid"))
    before = file_sha256(out / "audit.json")
    with pytest.raises(FileExistsError):
        run(out)
    assert file_sha256(out / "audit.json") == before


@pytest.mark.parametrize("change", ["source", "audio", "midi", "count", "case"])
def test_incorrect_binding_rejected(tmp_path, change):
    baseline = tmp_path / "baseline"
    baseline.mkdir()
    for name in ("inference.json", "normalized.wav", "raw.mid"):
        shutil.copyfile(BATCH_ROOT / CASE / "basic-pitch" / name, baseline / name)
    record = json.loads((baseline / "inference.json").read_text())
    if change in ("audio", "midi"):
        name = "normalized.wav" if change == "audio" else "raw.mid"
        with (baseline / name).open("ab") as f:
            f.write(b"changed")
    else:
        field = {"source": "source_sha256", "count": "raw_note_count", "case": "case_id"}[change]
        record[field] = "incorrect"
        (baseline / "inference.json").write_text(json.dumps(record))
    with pytest.raises(ValueError):
        verify(baseline)


def test_measurement_failure_is_recorded(tmp_path, monkeypatch):
    from scripts import run_real_partial_probe as runner

    def fail(*args):
        raise ValueError("measurement failed")

    monkeypatch.setattr(runner, "measure", fail)
    out = tmp_path / "failure"
    with pytest.raises(ValueError, match="measurement failed"):
        runner.run(out)
    assert json.loads((out / "status.json").read_text())["status"] == "failed"
    assert not (out / "audit.json").exists()
