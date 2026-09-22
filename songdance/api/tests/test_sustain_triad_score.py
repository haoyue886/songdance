import json
from xml.etree import ElementTree as ET

import pytest

from scripts.build_sustain_triad_score import arrange
from scripts.compare_piano_model_outputs import read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def event(pitch, time):
    return {"pitch": pitch, "start_sec": time, "end_sec": time + 1.6, "velocity": 70}


def test_grouping_preserves_non_template_pitches():
    events = [event(p, 0) for p in (56, 61, 66)]
    groups, changes = arrange(events)
    assert [n["pitch"] for n in groups[0]] == [56, 61, 66]
    assert [n["after"]["pitch"] for n in changes] == [56, 61, 66]
    assert all(n["after"]["end_sec"] == 2 for n in changes)


@pytest.mark.parametrize(
    "events",
    [
        [event(55, 0), event(60, 0)],
        [event(p, 0) for p in (55, 60, 64, 67)],
        [event(p, 0) for p in (55, 55, 64)],
        [event(p, 0.2) for p in (55, 60, 64)],
    ],
)
def test_bad_clusters_or_timing_cannot_be_forced_into_template(events):
    with pytest.raises(ValueError):
        arrange(events)


def test_actual_xml_midi_and_audit_agree_without_extra_tail_rest():
    folder = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-score-v2"
    report = json.loads((folder / "timeline.json").read_text())
    for name, digest in report["artifacts_sha256"].items():
        assert file_sha256(folder / name) == digest
    expected = sorted(
        (x["after"]["start_sec"], x["after"]["pitch"], x["after"]["end_sec"])
        for x in report["changes"]
    )
    midi = sorted(
        (n["start_sec"], n["pitch"], n["end_sec"]) for n in read_midi(folder / "score.mid")
    )
    assert midi == expected and len(midi) == 45 and max(n[2] for n in midi) == 30
    tree = ET.parse(folder / "score.musicxml")
    measures = tree.findall("./part/measure")
    assert len(measures) == 8 and measures[-1].get("implicit") == "yes"
    assert not tree.findall(".//rest")
    assert len(tree.findall(".//pitch")) == 45
    assert len(tree.findall(".//chord")) == 30
    assert report["structure"]["staff_count"] == 1
    assert report["structure"]["partial_final_measure_count"] == 1
    divisions = int(tree.findtext("./part/measure/attributes/divisions"))
    assert all(int(n.findtext("duration")) == 2 * divisions for n in tree.findall(".//note"))
    assert all(n.findtext("type") == "half" for n in tree.findall(".//note"))
    assert report["production_eligible"] is False
