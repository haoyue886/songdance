"""Isolated bass rhythm hypothesis; never fill missing notes or change treble."""

import copy
import hashlib
import json
from pathlib import Path
from xml.etree import ElementTree as ET


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revise(source: Path, destination: Path):
    if destination.exists():
        raise ValueError("destination already exists")
    tree = ET.parse(source)
    changes = []
    for measure in tree.findall("./part/measure"):
        children = list(measure)
        for index, note in enumerate(children[:-1]):
            rest = children[index + 1]
            if not (
                note.tag == rest.tag == "note"
                and note.findtext("staff") == rest.findtext("staff") == "2"
                and note.findtext("voice") == rest.findtext("voice")
                and note.find("pitch") is not None
                and rest.find("rest") is not None
                and note.findtext("duration") == "17640"
                and rest.findtext("duration") == "2520"
                and note.findtext("type") == "quarter"
                and len(note.findall("dot")) == 2
                and note.find("chord") is None
                and rest.find("chord") is None
            ):
                continue
            note.find("duration").text = "20160"
            note.find("type").text = "half"
            for dot in note.findall("dot"):
                note.remove(dot)
            measure.remove(rest)
            changes.append(
                {
                    "measure": measure.get("number"),
                    "before": 17640,
                    "after": 20160,
                    "absorbed_rest": 2520,
                }
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(destination, encoding="utf-8", xml_declaration=True)
    return changes


def timed_notes(path):
    result = []
    for measure in ET.parse(path).findall("./part/measure"):
        cursor = 0
        last = 0
        for node in measure:
            duration = int(node.findtext("duration", "0"))
            if node.tag == "backup":
                cursor -= duration
            elif node.tag == "forward":
                cursor += duration
            elif node.tag == "note":
                onset = last if node.find("chord") is not None else cursor
                if node.find("chord") is None:
                    last = cursor
                    cursor += duration
                if node.find("pitch") is not None:
                    result.append(
                        (
                            measure.get("number"),
                            node.findtext("staff"),
                            onset,
                            ET.tostring(node.find("pitch")),
                        )
                    )
    return result


def treble_nodes(path):
    return [
        ET.tostring(copy.deepcopy(n))
        for n in ET.parse(path).findall(".//note")
        if n.findtext("staff") == "1"
    ]


if __name__ == "__main__":
    from scripts.piano_comparison_cases import BATCH_ROOT, ROOT

    source = ROOT.parents[1] / "teacher-transkun-candidates-2026-09-16/10-device/candidate.musicxml"
    destination = BATCH_ROOT / "10-device/bass-rhythm-v2/score.musicxml"
    changes = revise(source, destination)
    assert timed_notes(source) == timed_notes(destination)
    assert treble_nodes(source) == treble_nodes(destination)
    report = {
        "production_eligible": False,
        "status": "rhythm_hypothesis_missing_bass_unresolved",
        "source_sha256": fingerprint(source),
        "output_sha256": fingerprint(destination),
        "changes": changes,
        "pitch_onsets_preserved": True,
        "treble_unchanged": True,
        "missing_C2_reference_seconds": [0, 15, 16],
    }
    destination.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Changed {len(changes)} bass durations; all pitch/onsets and treble unchanged")
