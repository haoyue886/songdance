import json
from pathlib import Path

import pytest

from scripts.generate_regression_set import build_pattern


def test_waltz_68_reference_contract_has_two_bass_beats_and_six_eighths():
    root = Path(__file__).parent / "fixtures/audio"
    manifest = json.loads((root / "waltz-68-reference-manifest.json").read_text())
    notes = build_pattern(manifest["case"]["pattern"])
    assert manifest["case"]["time_signature"] == "6/8"
    assert len(notes) == 152
    for measure in range(2):
        start = measure * 1.5
        treble = [note for note in notes if start <= note.start < start + 1.5 and note.pitch >= 60]
        assert len(treble) == 6
        assert all(note.end - note.start == pytest.approx(0.25) for note in treble)
    bass = [note for note in notes if note.pitch < 60]
    assert all(note.end - note.start == pytest.approx(0.75) for note in bass)


def test_legacy_waltz_34_remains_three_four():
    notes = build_pattern("waltz_34")
    assert len(notes) > 0
    assert [note.pitch for note in notes[:3]] == [48, 60, 64]
