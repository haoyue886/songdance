"""Research-only 10-device duration candidate."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT


def run():
    d = BATCH_ROOT / "10-device/transkun-v2"
    midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
    notes = sorted([n for i in midi.instruments for n in i.notes], key=lambda n: n.start)
    highs = [n for n in notes if n.pitch >= 60]
    events = []
    for n in notes:
        hand = "left" if n.pitch < 60 else "right"
        if hand == "left":
            end = n.start + 0.9
        else:
            later = [x.start for x in highs if x.start > n.start]
            end = min(n.end, (min(later) - 0.01) if later else n.end)
        events.append(
            NoteEvent(n.start, max(end, n.start + 0.05), n.pitch, n.velocity, 0.99, hand=hand)
        )
    out = d / "duration-candidate.musicxml"
    write_musicxml(build_score(events, title="Transkun 10-device duration"), out)
    s = read_musicxml_structure(out)
    r = {
        "case_id": "10-device",
        "events": len(events),
        "structure": s,
        "production_eligible": False,
    }
    (d / "duration-validation.json").write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    run()
