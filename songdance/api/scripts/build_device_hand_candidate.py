"""Build isolated fixed-hand candidate for 10-device."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT


def run():
    case = "10-device"
    d = BATCH_ROOT / case / "transkun-v2"
    midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
    events = [
        NoteEvent(
            n.start, n.end, n.pitch, n.velocity, 0.99, hand="left" if n.pitch < 60 else "right"
        )
        for i in midi.instruments
        for n in i.notes
    ]
    out = d / "fixed-hand-candidate.musicxml"
    write_musicxml(build_score(events, title="Transkun 10-device fixed hands"), out)
    s = read_musicxml_structure(out)
    result = {
        "case_id": case,
        "event_count": len(events),
        "low_count": sum(e.hand == "left" for e in events),
        "high_count": sum(e.hand == "right" for e in events),
        "structure": s,
        "production_eligible": False,
    }
    (d / "fixed-hand-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    run()
