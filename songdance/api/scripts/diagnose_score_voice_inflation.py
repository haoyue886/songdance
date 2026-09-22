"""Diagnose raw overlap versus MusicXML voice inflation for isolated model candidates."""

import json

import pretty_midi

from app.pipeline.score_io import read_musicxml_structure
from scripts.piano_comparison_cases import BATCH_ROOT, CASE_IDS


def run():
    rows = []
    for case in CASE_IDS:
        d = BATCH_ROOT / case / "transkun-v2"
        midi = pretty_midi.PrettyMIDI(str(d / "raw.mid"))
        notes = sorted((n.start, n.end, n.pitch) for i in midi.instruments for n in i.notes)
        overlap_pairs = sum(1 for a, b in zip(notes, notes[1:], strict=False) if b[0] < a[1] - 1e-3)
        xml = read_musicxml_structure(d / "candidate.musicxml")
        rows.append(
            {
                "case_id": case,
                "raw_events": len(notes),
                "raw_overlap_adjacent_pairs": overlap_pairs,
                "musicxml_voices": xml["voice_count"],
                "musicxml_rests": xml["rest_count"],
                "voice_to_event_ratio": round(xml["voice_count"] / len(notes), 3),
                "rest_to_event_ratio": round(xml["rest_count"] / len(notes), 3),
            }
        )
    out = BATCH_ROOT / "voice-inflation-diagnostic.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    run()
