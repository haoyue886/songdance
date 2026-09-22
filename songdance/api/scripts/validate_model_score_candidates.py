"""Build isolated MusicXML from raw candidate MIDI and validate parser structure."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT, CASE_IDS
from scripts.score_parser_validation import validate_external_parsers


def run():
    rows = []
    for case in CASE_IDS:
        d = BATCH_ROOT / case / "transkun-v2"
        midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
        events = [
            NoteEvent(n.start, n.end, n.pitch, n.velocity, 0.99)
            for i in midi.instruments
            for n in i.notes
        ]
        out = d / "candidate.musicxml"
        write_musicxml(build_score(events, title=f"Transkun {case}"), out)
        structure = read_musicxml_structure(out)
        parsers = validate_external_parsers([out])[str(out.resolve())]
        rows.append(
            {
                "case_id": case,
                "event_count": len(events),
                "structure": structure,
                "parser_validation": parsers,
                "production_eligible": False,
            }
        )
    target = BATCH_ROOT / "score-validation.json"
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    run()
