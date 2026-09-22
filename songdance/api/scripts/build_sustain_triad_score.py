"""Notation-only hypothesis from model events; no reference pitch template."""

import json
from pathlib import Path
from statistics import mean
from xml.etree import ElementTree as ET

import pretty_midi
from music21 import chord, clef, instrument, metadata, meter, stream, tempo

from app.pipeline.score_io import read_musicxml_structure
from scripts.piano_comparison_cases import ROOT, file_sha256


def arrange(events):
    groups = []
    for event in sorted(events, key=lambda n: (n["start_sec"], n["pitch"])):
        if not groups or event["start_sec"] - groups[-1][0]["start_sec"] > 0.08:
            groups.append([event])
        else:
            groups[-1].append(event)
    if not groups or any(len(g) != 3 or len({n["pitch"] for n in g}) != 3 for g in groups):
        raise ValueError("requires exactly three distinct model pitches per onset cluster")
    changes = []
    for i, group in enumerate(groups):
        target = i * 2.0
        for event in group:
            if abs(event["start_sec"] - target) > 0.05:
                raise ValueError("model onset does not fit the proposed two-second grid")
            changes.append(
                {
                    "before": dict(event),
                    "after": {**event, "start_sec": target, "end_sec": target + 2},
                }
            )
    return groups, changes


def run(output: Path):
    source = ROOT / "tests/fixtures/audio/candidates/06-teacher-triad-models-v1/missing-notes-v2"
    audit_path = source / "audit.json"
    audit = json.loads(audit_path.read_text())
    if audit["midi_sha256"] != file_sha256(source / "candidate.mid"):
        raise ValueError("model candidate changed")
    groups, changes = arrange(audit["events"])
    output.mkdir(exist_ok=False, parents=True)
    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = "06 - Three-note chord candidate"
    part = stream.Part(id="Piano")
    part.insert(0, instrument.Piano())
    for start in range(0, len(groups), 2):
        measure = stream.Measure(number=start // 2 + 1)
        if start == 0:
            measure.insert(0, clef.TrebleClef())
            measure.insert(0, meter.TimeSignature("4/4"))
            measure.insert(0, tempo.MetronomeMark(number=60))
        for i, group in enumerate(groups[start : start + 2]):
            c = chord.Chord([n["pitch"] for n in group], quarterLength=2)
            c.volume.velocity = round(mean(n["velocity"] for n in group))
            measure.insert(i * 2, c)
        part.append(measure)
    score.insert(0, part)
    xml = output / "score.musicxml"
    score.write("musicxml", fp=str(xml))
    # Explicitly mark the last incomplete measure; don't invent time or rests.
    if len(groups) % 2:
        tree = ET.parse(xml)
        last = tree.findall("./part/measure")[-1]
        last.set("implicit", "yes")
        # music21 fills the final bar when exporting. Remove only its verified
        # generated half-rest; all model-derived chord notes remain untouched.
        rests = [n for n in last.findall("note") if n.find("rest") is not None]
        divisions = int(tree.findtext("./part/measure/attributes/divisions"))
        if len(rests) != 1 or int(rests[0].findtext("duration")) != 2 * divisions:
            raise ValueError("unexpected terminal rest: refuse automatic removal")
        last.remove(rests[0])
        tree.write(xml, encoding="utf-8", xml_declaration=True)
    midi = pretty_midi.PrettyMIDI(initial_tempo=60)
    midi.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    piano = pretty_midi.Instrument(0)
    piano.notes = [
        pretty_midi.Note(
            x["after"]["velocity"],
            x["after"]["pitch"],
            x["after"]["start_sec"],
            x["after"]["end_sec"],
        )
        for x in changes
    ]
    midi.instruments.append(piano)
    midi.write(str(output / "score.mid"))
    report = {
        "production_eligible": False,
        "status": "notation_hypothesis_not_teacher_approved",
        "source_kind": "new_synthetic_teacher_pattern_not_original_audio",
        "source_audit_sha256": file_sha256(audit_path),
        "script_sha256": file_sha256(Path(__file__)),
        "notation": {
            "tempo": 60,
            "meter": "4/4",
            "source": "explicit_presentation_hypothesis",
            "chord_quarter_length": 2,
            "pedal": "not_inferred",
        },
        "changes": changes,
        "structure": read_musicxml_structure(xml),
        "artifacts_sha256": {
            name: file_sha256(output / name) for name in ("score.musicxml", "score.mid")
        },
        "musescore_validation": "not_run",
    }
    (output / "timeline.json").write_text(json.dumps(report, indent=2))
    print(
        {
            k: report["structure"][k]
            for k in [
                "staff_count",
                "chord_count",
                "rest_count",
                "measure_duration_error_count",
                "partial_final_measure_count",
            ]
        }
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
