"""Validate human annotation completeness, not musical truth or deletion safety."""

import argparse
import json
from math import isfinite
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.piano_comparison_cases import BATCH_ROOT, case_inputs, file_sha256
from scripts.prepare_repeat_annotations import candidates
from scripts.run_real_partial_probe import CASE, verify


def validate(directory: Path) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text())
    labels = json.loads((directory / "labels.json").read_text())
    if labels.get("manifest_sha256") != file_sha256(directory / "manifest.json"):
        raise ValueError("manifest binding changed")
    if not isinstance(labels.get("reviewer"), str) or not labels["reviewer"].strip():
        raise ValueError("human reviewer required")
    source, _, provenance = case_inputs(CASE)
    baseline = BATCH_ROOT / CASE / "basic-pitch"
    _, raw = verify(baseline)
    if (
        manifest.get("source_sha256") != file_sha256(source)
        or manifest.get("raw_sha256") != file_sha256(baseline / "raw.mid")
        or manifest.get("source_provenance") != provenance
    ):
        raise ValueError("source binding changed")
    pcm, rate = sf.read(source, dtype="int16", always_2d=True)
    if manifest.get("sample_rate") != rate:
        raise ValueError("sample rate changed")
    expected_rows = candidates(raw)
    if len(manifest["candidates"]) != len(expected_rows):
        raise ValueError("candidate selection changed")
    for row, original in zip(manifest["candidates"], expected_rows, strict=True):
        if any(row.get(k) != v for k, v in original.items()):
            raise ValueError("candidate identity changed")
    expected = {r["id"]: r for r in manifest["candidates"]}
    rows = labels.get("labels", [])
    if len(rows) != len(expected) or {r["id"] for r in rows} != set(expected):
        raise ValueError("candidate identities incomplete or duplicated")
    for row in rows:
        item = expected[row["id"]]
        path = (directory / item["clip_file"]).resolve()
        if not path.is_relative_to(directory.resolve()) or file_sha256(path) != item["clip_sha256"]:
            raise ValueError("clip binding changed")
        start_sample = max(0, int((item["previous_model_event"]["start_sec"] - 0.3) * rate))
        stop_sample = min(len(pcm), int((item["model_event"]["start_sec"] + 0.5) * rate))
        if (
            item["start_sample"] != start_sample
            or item["stop_sample"] != stop_sample
            or item["candidate_local_sec"] != item["model_event"]["start_sec"] - start_sample / rate
        ):
            raise ValueError("clip time mapping changed")
        clip, clip_rate = sf.read(path, dtype="int16", always_2d=True)
        if clip_rate != rate or not np.array_equal(clip, pcm[start_sample:stop_sample]):
            raise ValueError("clip PCM differs from source")
        if row.get("judgment") not in ("restrike", "no_restrike"):
            raise ValueError("pending or uncertain labels remain")
        if not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError("review evidence notes required")
        pitch, onset = row.get("confirmed_pitch"), row.get("confirmed_onset_sec")
        if row["judgment"] == "restrike":
            if type(pitch) is not int or not 21 <= pitch <= 108:
                raise ValueError("confirmed piano MIDI pitch required")
            if type(onset) not in (int, float) or not isfinite(onset):
                raise ValueError("finite source-relative onset required")
            start = item["start_sample"] / manifest["sample_rate"]
            stop = item["stop_sample"] / manifest["sample_rate"]
            if not start <= onset < stop:
                raise ValueError("onset outside source clip")
        elif pitch is not None or onset is not None:
            raise ValueError("no_restrike must not contain confirmed note")
    return {
        "status": "complete_human_form_only",
        "label_count": len(rows),
        "production_eligible": False,
        "deletion_authorized": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    print(json.dumps(validate(parser.parse_args().directory)))
