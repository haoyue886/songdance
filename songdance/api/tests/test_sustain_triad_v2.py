import json
from pathlib import Path

import pytest

from scripts.build_sustain_triad_candidate import candidate_settings
from scripts.generate_regression_set import build_pattern


def test_sustain_triad_v2_matches_teacher_candidate_contract():
    manifest = json.loads(
        (Path(__file__).parent / "fixtures/audio/sustain-triad-v2-manifest.json").read_text()
    )
    case = manifest["case"]
    notes = build_pattern(case["pattern"])
    expected_chords = [tuple(values) for values in case["chords_midi"]]
    assert len(notes) == 45
    assert all(
        note.end - note.start == pytest.approx(case["note_duration_seconds"]) for note in notes
    )
    groups = {}
    for note in notes:
        groups.setdefault(note.start, []).append(note.pitch)
    actual = [tuple(groups[start]) for start in sorted(groups)]
    assert all(chord == expected_chords[index % 3] for index, chord in enumerate(actual))
    assert all(
        right - left == pytest.approx(case["onset_interval_seconds"])
        for left, right in zip(sorted(groups), sorted(groups)[1:], strict=False)
    )


def test_legacy_sustain_pattern_remains_four_note_truth():
    notes = build_pattern("sustain")
    first = [note.pitch for note in notes if note.start == 0]
    assert first == [48, 55, 60, 64]


def test_candidate_builder_consumes_versioned_manifest_settings():
    settings = candidate_settings()
    assert settings == {
        "id": "06-sustain-triad-v2",
        "pattern": "sustain_triad_v2",
        "duration_seconds": 30,
        "sample_rate": 22050,
        "noise": 0.0,
        "device_bandwidth": False,
        "synthesis_seed": 9006,
    }
