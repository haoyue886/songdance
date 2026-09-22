"""Explicit monophonic notation stage; no automatic texture or tempo claim."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from app.pipeline.score import NotationContext, build_score, write_musicxml, write_quantized_midi
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.piano_comparison_cases import file_sha256


def melody_events(notes):
    ordered = sorted(notes, key=lambda n: (n["start_sec"], n["pitch"]))
    if not ordered or any(n["pitch"] < 60 for n in ordered):
        raise ValueError("confirmed-monophonic profile requires nonempty treble-only events")
    if any(
        b["start_sec"] - a["start_sec"] <= 0.08 for a, b in zip(ordered, ordered[1:], strict=False)
    ):
        raise ValueError("simultaneous/dense notes require a different profile")
    events, changes = [], []
    for index, note in enumerate(ordered):
        end = note["end_sec"]
        if index + 1 < len(ordered):
            end = min(end, ordered[index + 1]["start_sec"] - 0.01)
        if end <= note["start_sec"]:
            raise ValueError("invalid note duration")
        # Numeric unknown placeholder for the existing score API; not a probability.
        events.append(
            NoteEvent(note["start_sec"], end, note["pitch"], note["velocity"], 0.0, hand="right")
        )
        changes.append(
            {
                "raw": note,
                "trimmed_end_sec": end,
                "reason": "confirmed_monophonic_next_attack"
                if end != note["end_sec"]
                else "unchanged",
            }
        )
    return events, changes


def run(source: Path, output: Path, tempo: int, time_signature: str):
    if tempo <= 0 or time_signature not in ("4/4", "3/4", "2/4", "6/8"):
        raise ValueError("invalid explicit notation tempo/meter")
    pipeline = json.loads((source / "pipeline.json").read_text())
    if pipeline.get("status") != "complete" or pipeline.get("production_eligible") is not False:
        raise ValueError("requires completed research raw inference")
    for name, digest in pipeline["artifacts_sha256"].items():
        path = (source / name).resolve()
        if not path.is_relative_to(source.resolve()) or file_sha256(path) != digest:
            raise ValueError("raw inference artifact changed")
    raw = json.loads((source / "raw-timeline.json").read_text())
    events, changes = melody_events(raw["notes"])
    output.mkdir(exist_ok=False, parents=True)
    report = {
        "status": "running",
        "production_eligible": False,
        "profile": "confirmed-monophonic",
        "input_pipeline_sha256": file_sha256(source / "pipeline.json"),
        "script_sha256": file_sha256(Path(__file__)),
        "notation_configuration": {
            "tempo_bpm": tempo,
            "meter": time_signature,
            "source": "explicit_operator_configuration",
        },
        "confidence_semantics": "raw unknown; score adapter uses numeric zero placeholder",
        "hand_semantics": "right is assigned by explicit profile; not inferred by model",
        "changes": changes,
    }
    status = output / "notation.json"
    try:
        context = NotationContext(
            texture_hint="monophonic_melody",
            tempo_bpm=tempo,
            tempo_source="explicit_operator_configuration",
            time_signature=time_signature,
            time_signature_source="explicit_operator_configuration",
        )
        scored = build_score(events, title="Monophonic candidate", notation_context=context)
        if Counter(n.pitch for n in scored.notes) != Counter(n.pitch for n in events):
            raise ValueError("notation changed input pitches/count")
        write_musicxml(scored, output / "score.musicxml")
        write_quantized_midi(scored, output / "score.mid")
        structure = read_musicxml_structure(output / "score.musicxml")
        if structure["staff_count"] != 1:
            raise ValueError("confirmed monophonic notation did not produce one staff")
        ordered_score = sorted(scored.notes, key=lambda n: (n.start_sec, n.pitch))
        if [n.pitch for n in ordered_score] != [n.pitch for n in events]:
            raise ValueError("notation changed melodic pitch order")
        notes = [
            {
                **asdict(n),
                "confidence": None,
                "hand_confidence": None,
                "hand_source": "explicit_monophonic_profile",
            }
            for n in ordered_score
        ]
        for change, note in zip(changes, notes, strict=True):
            change["notated"] = note
            change["onset_shift_seconds"] = note["start_sec"] - change["raw"]["start_sec"]
        (output / "timeline.json").write_text(
            json.dumps(
                {
                    "production_eligible": False,
                    "model": raw["model"],
                    "notes": notes,
                    "changes": changes,
                },
                indent=2,
            )
            + "\n"
        )
        report.update(
            status="complete_candidate_only",
            structure=structure,
            artifacts_sha256={
                name: file_sha256(output / name)
                for name in ("score.musicxml", "score.mid", "timeline.json")
            },
            musescore_validation="not_run",
            teacher_review="not_inferred_from_other_versions",
        )
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        status.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tempo", type=int, required=True)
    parser.add_argument("--meter", required=True)
    parser.add_argument("--profile", choices=["confirmed-monophonic"], required=True)
    args = parser.parse_args()
    print(run(args.input, args.output, args.tempo, args.meter)["status"])
