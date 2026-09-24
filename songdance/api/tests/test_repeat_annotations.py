import json

import numpy as np
import pytest
import soundfile as sf

from scripts.piano_comparison_cases import case_inputs
from scripts.prepare_repeat_annotations import prepare
from scripts.run_real_partial_probe import CASE
from scripts.validate_repeat_annotations import validate


def test_pcm_pending_and_complete_form(tmp_path):
    out = tmp_path / "labels"
    manifest = prepare(out)
    pcm, rate = sf.read(case_inputs(CASE)[0], dtype="int16", always_2d=True)
    assert len(manifest["candidates"]) == 120
    for row in manifest["candidates"]:
        clip, actual_rate = sf.read(out / row["clip_file"], dtype="int16", always_2d=True)
        assert actual_rate == rate
        assert np.array_equal(clip, pcm[row["start_sample"] : row["stop_sample"]])
    with pytest.raises(ValueError, match="reviewer"):
        validate(out)
    labels = json.loads((out / "labels.json").read_text())
    labels["reviewer"] = "test fixture only"
    for row in labels["labels"]:
        row.update(judgment="no_restrike", notes="synthetic test form, not actual review")
    (out / "labels.json").write_text(json.dumps(labels))
    assert validate(out)["deletion_authorized"] is False
    row = labels["labels"][0]
    row.update(
        judgment="restrike",
        confirmed_pitch=60,
        confirmed_onset_sec=manifest["candidates"][0]["model_event"]["start_sec"],
    )
    (out / "labels.json").write_text(json.dumps(labels))
    assert validate(out)["label_count"] == 120
    for field, value in [
        ("confirmed_pitch", True),
        ("confirmed_onset_sec", float("nan")),
        ("confirmed_onset_sec", -1),
        ("judgment", "uncertain"),
        ("notes", ""),
    ]:
        bad = json.loads(json.dumps(labels))
        bad["labels"][0][field] = value
        (out / "labels.json").write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            validate(out)
    (out / "labels.json").write_text(json.dumps(labels))
    (out / manifest["candidates"][0]["clip_file"]).write_bytes(b"broken")
    with pytest.raises(ValueError, match="clip"):
        validate(out)
    with pytest.raises(FileExistsError):
        prepare(out)


@pytest.mark.parametrize("change", ["time", "pcm", "rate", "missing", "duplicate"])
def test_rebinding_manifest_cannot_hide_changed_source(tmp_path, change):
    from scripts.piano_comparison_cases import file_sha256

    out = tmp_path / "data"
    manifest = prepare(out)
    labels = json.loads((out / "labels.json").read_text())
    labels["reviewer"] = "test only"
    for row in labels["labels"]:
        row.update(judgment="no_restrike", notes="fixture only")
    item = manifest["candidates"][0]
    if change == "time":
        item["start_sample"] += 1
    elif change == "rate":
        manifest["sample_rate"] += 1
    elif change == "pcm":
        path = out / item["clip_file"]
        clip, rate = sf.read(path, dtype="int16", always_2d=True)
        clip[0, 0] = 0 if clip[0, 0] else 1
        sf.write(path, clip, rate, subtype="PCM_16")
        item["clip_sha256"] = file_sha256(path)
    elif change == "missing":
        labels["labels"].pop()
    else:
        labels["labels"][1] = labels["labels"][0]
    (out / "manifest.json").write_text(json.dumps(manifest))
    labels["manifest_sha256"] = file_sha256(out / "manifest.json")
    (out / "labels.json").write_text(json.dumps(labels))
    with pytest.raises(ValueError):
        validate(out)
