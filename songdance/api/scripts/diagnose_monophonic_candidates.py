"""Research-only monophonic evidence for weak/device candidates."""

import json

import pretty_midi

from scripts.piano_comparison_cases import BATCH_ROOT


def run():
    rows = []
    for case in ("07-soft", "10-device"):
        midi = pretty_midi.PrettyMIDI(str(BATCH_ROOT / case / "transkun-v2/raw.mid"))
        notes = sorted([n for i in midi.instruments for n in i.notes], key=lambda n: n.start)
        clusters = []
        for n in notes:
            if not clusters or n.start - clusters[-1][-1].start > 0.08:
                clusters.append([n])
            else:
                clusters[-1].append(n)
        simultaneous = sum(len(c) > 1 for c in clusters)
        low = sum(n.pitch < 60 for n in notes)
        rows.append(
            {
                "case_id": case,
                "events": len(notes),
                "onset_clusters": len(clusters),
                "simultaneous_clusters": simultaneous,
                "low_register_events": low,
                "monophonic_candidate": simultaneous == 0 and low == 0,
                "production_eligible": False,
            }
        )
    out = BATCH_ROOT / "monophonic-diagnostic.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    run()
