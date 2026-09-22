"""Explicit offline cases; real recordings never borrow synthetic reference MIDI."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_ROOT = ROOT / "tests/fixtures/audio"
CASE_IDS = ("06-sustain", "07-soft", "10-device", "14-hand-crossing", "02-brahms-intermezzo")
DEFAULT_CASE = "14-hand-crossing"
BATCH_ROOT = AUDIO_ROOT / "candidates/piano-model-comparison-expanded-v1"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def case_inputs(case_id: str) -> tuple[Path, Path | None, dict]:
    if case_id not in CASE_IDS:
        raise ValueError(f"unsupported comparison case: {case_id}")
    if case_id == "02-brahms-intermezzo":
        wav = AUDIO_ROOT / "human-generated" / f"{case_id}.wav"
        provenance_path = AUDIO_ROOT / "human-provenance.json"
        entry = next(
            x for x in json.loads(provenance_path.read_text())["cases"] if x["id"] == case_id
        )
        if file_sha256(wav) != entry["clip_sha256"]:
            raise ValueError("real recording does not match its source provenance")
        if entry["license"] not in ("Public domain", "CC BY-SA 3.0"):
            raise ValueError("real recording license is not in the approved fixture list")
        return (
            wav,
            None,
            {
                "kind": "real_piano_without_note_reference",
                "provenance_sha256": file_sha256(provenance_path),
                "record": entry,
            },
        )
    return (
        AUDIO_ROOT / "generated" / f"{case_id}.wav",
        AUDIO_ROOT / "generated" / f"{case_id}.mid",
        {"kind": "synthetic_regression_fixture", "license": "CC0-1.0"},
    )
