"""Research-only onset grouping for Transkun candidates; never used by production."""

import json

import pretty_midi

from scripts.piano_comparison_cases import BATCH_ROOT, CASE_IDS


def group(notes):
    ordered = sorted(notes, key=lambda n: (n.start, n.pitch))
    result = []
    last_pitch = None
    last_hand = None
    for n in ordered:
        if last_pitch is None:
            hand = "left" if n.pitch < 60 else "right"
            reason = "register_seed"
        else:
            hand = "left" if n.pitch < 60 else "right"
            if abs(n.pitch - last_pitch) <= 4 and last_hand:
                hand = last_hand
                reason = "continuity"
            else:
                reason = "register_boundary"
        result.append(
            {
                "pitch": n.pitch,
                "start_sec": n.start,
                "original_end_sec": n.end,
                "hand_candidate": hand,
                "decision": "retain",
                "reason": reason,
            }
        )
        last_pitch = n.pitch
        last_hand = hand
    for index, event in enumerate(result):
        same_hand = [
            item["start_sec"]
            for item in result[index + 1 :]
            if item["hand_candidate"] == event["hand_candidate"]
            and item["start_sec"] > event["start_sec"]
        ]
        next_start = min(same_hand) if same_hand else None
        if next_start is not None and event["original_end_sec"] > next_start:
            event["suggested_end_sec"] = round(next_start, 6)
            event["duration_action"] = "suggest_trim_within_hand"
            event["duration_reason"] = "same_hand_next_onset"
        else:
            event["suggested_end_sec"] = event["original_end_sec"]
            event["duration_action"] = "retain_duration"
            event["duration_reason"] = "no_same_hand_overlap"
        if (
            event["original_end_sec"] - event["start_sec"] > 1.5
            and event["duration_action"] == "retain_duration"
        ):
            event["decision"] = "review"
            event["duration_reason"] = "long_duration_without_same_hand_boundary"
    return result


def run():
    rows = []
    for case in CASE_IDS[:-1]:
        midi = pretty_midi.PrettyMIDI(str(BATCH_ROOT / case / "transkun-v2/raw.mid"))
        notes = [n for i in midi.instruments for n in i.notes]
        events = group(notes)
        rows.append(
            {
                "case_id": case,
                "event_count": len(events),
                "left_count": sum(e["hand_candidate"] == "left" for e in events),
                "right_count": sum(e["hand_candidate"] == "right" for e in events),
                "review_count": sum(e["decision"] == "review" for e in events),
                "production_eligible": False,
                "events": events,
            }
        )
    out = BATCH_ROOT / "voice-grouping-prototype.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "cases": len(rows),
                "events": sum(x["event_count"] for x in rows),
                "production_eligible": False,
            }
        )
    )


if __name__ == "__main__":
    run()
