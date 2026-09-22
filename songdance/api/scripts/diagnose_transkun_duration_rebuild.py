"""Evaluate onset-priority duration reconstruction without changing production."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT, CASE_IDS


def run():
    rows = []
    for case in CASE_IDS:
        d = BATCH_ROOT / case / "transkun-v2"
        midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
        notes = sorted(
            (n.start, n.end, n.pitch, n.velocity) for i in midi.instruments for n in i.notes
        )
        starts = sorted({n[0] for n in notes})
        events = []
        for start, end, pitch, velocity in notes:
            next_start = next((x for x in starts if x > start), start + 0.5)
            rebuilt_end = min(end, next_start - 0.01)
            if rebuilt_end <= start:
                rebuilt_end = start + 0.05
            events.append(NoteEvent(start, rebuilt_end, pitch, velocity, 0.99))
        out = d / "duration-rebuild.musicxml"
        write_musicxml(build_score(events, title=f"Transkun duration rebuild {case}"), out)
        s = read_musicxml_structure(out)
        rows.append(
            {
                "case_id": case,
                "raw_events": len(notes),
                "musicxml_voices": s["voice_count"],
                "musicxml_rests": s["rest_count"],
                "measure_duration_errors": s["measure_duration_error_count"],
                "time_signatures": s["time_signatures"],
                "production_eligible": False,
            }
        )
    (BATCH_ROOT / "duration-rebuild-diagnostic.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    run()
