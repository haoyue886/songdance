"""Research-only synchronized chord-duration candidate for 06-sustain."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT


def run():
    d = BATCH_ROOT / "06-sustain/transkun-v2"
    notes = sorted(
        [n for i in pretty_midi.PrettyMIDI(str(d / "raw.mid")).instruments for n in i.notes],
        key=lambda n: n.start,
    )
    clusters = []
    for n in notes:
        if not clusters or n.start - clusters[-1][0].start > 0.08:
            clusters.append([n])
        else:
            clusters[-1].append(n)
    starts = [c[0].start for c in clusters]
    events = []
    for c_index, c in enumerate(clusters):
        boundary = (
            starts[c_index + 1] - 0.01 if c_index + 1 < len(starts) else max(n.end for n in c)
        )
        for n in c:
            events.append(
                NoteEvent(
                    n.start, min(max(n.end, n.start + 0.05), boundary), n.pitch, n.velocity, 0.99
                )
            )
    out = d / "chord-sync-candidate.musicxml"
    write_musicxml(build_score(events, title="Transkun 06-sustain chord sync"), out)
    s = read_musicxml_structure(out)
    r = {
        "case_id": "06-sustain",
        "events": len(events),
        "clusters": len(clusters),
        "structure": s,
        "production_eligible": False,
    }
    (d / "chord-sync-validation.json").write_text(
        json.dumps(r, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    run()
