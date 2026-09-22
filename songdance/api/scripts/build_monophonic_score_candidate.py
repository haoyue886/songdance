"""Build isolated single-staff candidate for verified monophonic case."""

import json

import pretty_midi

from app.pipeline.score import NotationContext, build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT


def run():
    case = "07-soft"
    d = BATCH_ROOT / case / "transkun-v2"
    midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
    notes = sorted([n for i in midi.instruments for n in i.notes], key=lambda n: n.start)
    events = []
    for index, n in enumerate(notes):
        next_start = notes[index + 1].start if index + 1 < len(notes) else n.end
        events.append(
            NoteEvent(
                n.start, min(n.end, next_start - 0.01), n.pitch, n.velocity, 0.99, hand="right"
            )
        )
    out = d / "monophonic-candidate.musicxml"
    write_musicxml(
        build_score(
            events,
            title="Transkun 07-soft monophonic",
            notation_context=NotationContext(texture_hint="monophonic_melody"),
        ),
        out,
    )
    s = read_musicxml_structure(out)
    result = {
        "case_id": case,
        "event_count": len(events),
        "structure": s,
        "production_eligible": False,
    }
    (d / "monophonic-validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    run()
