"""Report review differences without carrying ratings to rebuilt files."""

import argparse
import json
from pathlib import Path

from music21 import chord, converter

from scripts.compare_piano_model_outputs import read_midi
from scripts.human_quality_gate import file_sha256
from scripts.rebuild_review_isolated import SOURCE


def midi_signature(path):
    return sorted(
        (n["pitch"], round(n["start_sec"], 6), round(n["end_sec"], 6), n["velocity"])
        for n in read_midi(path)
    )


def xml_signature(path):
    score = converter.parse(str(path))
    parts = []
    for part in score.parts:
        items = []
        for n in part.recurse().notesAndRests:
            pitches = (
                tuple(sorted(p.midi for p in n.pitches))
                if isinstance(n, chord.Chord)
                else ((n.pitch.midi,) if n.isNote else ())
            )
            items.append(
                (float(n.getOffsetInHierarchy(part)), float(n.duration.quarterLength), pitches)
            )
        parts.append(sorted(items))
    return parts


def compare(root):
    state = json.loads((root / "rebuild.json").read_text())
    if state["status"] != "complete_pending_review":
        raise ValueError("rebuild is not complete")
    rows = []
    for suite, manifest in [("structure", "manifest.json"), ("human", "human-manifest.json")]:
        for case in json.loads((root / manifest).read_text())["cases"]:
            case_id = case["id"]
            old = SOURCE / f"{suite}-review-artifacts" / case_id
            new = root / f"{suite}-review-artifacts" / case_id
            files = {
                name: {"old": file_sha256(old / name), "new": file_sha256(new / name)}
                for name in ("raw.mid", "score.mid", "score.musicxml", "timeline.json")
            }
            rows.append(
                {
                    "suite": suite,
                    "case_id": case_id,
                    "files": files,
                    "raw_events_equal": midi_signature(old / "raw.mid")
                    == midi_signature(new / "raw.mid"),
                    "score_events_equal": midi_signature(old / "score.mid")
                    == midi_signature(new / "score.mid"),
                    "xml_note_rest_timing_equal": xml_signature(old / "score.musicxml")
                    == xml_signature(new / "score.musicxml"),
                    "review_status": "pending_no_rating_transfer",
                }
            )
    report = {
        "production_eligible": False,
        "rebuild_sha256": file_sha256(root / "rebuild.json"),
        "script_sha256": file_sha256(Path(__file__)),
        "cases": rows,
        "limitation": "semantic comparison is not visual validation; no human rating transfer",
    }
    with (root / "differences.json").open("x") as handle:
        json.dump(report, handle, indent=2)
    for row in rows:
        print(
            row["suite"],
            row["case_id"],
            row["raw_events_equal"],
            row["score_events_equal"],
            row["xml_note_rest_timing_equal"],
        )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    compare(parser.parse_args().directory)
