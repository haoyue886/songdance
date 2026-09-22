"""Build isolated MusicXML from research-only grouped duration suggestions."""

import json

import pretty_midi

from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import BATCH_ROOT, CASE_IDS


def run():
    groups = {
        x["case_id"]: x
        for x in json.loads((BATCH_ROOT / "voice-grouping-prototype.json").read_text())
    }
    rows = []
    for case in CASE_IDS[:-1]:
        notes = [
            n
            for i in pretty_midi.PrettyMIDI(
                str(BATCH_ROOT / case / "transkun-v2/raw.mid")
            ).instruments
            for n in i.notes
        ]
        events = []
        for n, e in zip(
            sorted(notes, key=lambda n: (n.start, n.pitch)), groups[case]["events"], strict=True
        ):
            end = (
                e["suggested_end_sec"]
                if e["duration_action"] == "suggest_trim_within_hand"
                else n.end
            )
            events.append(
                NoteEvent(
                    n.start,
                    max(end, n.start + 0.03),
                    n.pitch,
                    n.velocity,
                    0.99,
                    hand=e["hand_candidate"],
                )
            )
        out = BATCH_ROOT / case / "grouped-candidate.musicxml"
        write_musicxml(build_score(events, title=f"Grouped {case}"), out)
        s = read_musicxml_structure(out)
        rows.append(
            {
                "case_id": case,
                "events": len(events),
                "voices": s["voice_count"],
                "rests": s["rest_count"],
                "measure_duration_errors": s["measure_duration_error_count"],
                "production_eligible": False,
            }
        )
    (BATCH_ROOT / "grouped-score-validation.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    run()
