from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree

import pretty_midi
from music21 import converter

from app.pipeline.errors import ScoreGenerationError
from app.pipeline.score_validation import (
    raise_for_structure_errors,
    score_structure_summary,
)
from app.pipeline.voicing import notation_hand

if TYPE_CHECKING:
    from app.pipeline.score import ScoredTranscription


def write_quantized_midi(scored: "ScoredTranscription", destination: Path) -> None:
    try:
        midi = pretty_midi.PrettyMIDI(initial_tempo=scored.tempo_bpm)
        numerator, denominator = map(int, scored.analysis.time_signature.split("/", 1))
        midi.time_signature_changes.append(pretty_midi.TimeSignature(numerator, denominator, 0.0))
        for hand in ("right", "left"):
            piano = pretty_midi.Instrument(program=0, name="Piano")
            for event in sorted(
                (item for item in scored.notes if notation_hand(item) == hand),
                key=lambda item: (item.start_sec, item.pitch, item.end_sec),
            ):
                start = max(0.0, event.start_sec)
                piano.notes.append(
                    pretty_midi.Note(
                        velocity=event.velocity,
                        pitch=event.pitch,
                        start=start,
                        end=max(start + 1e-6, event.end_sec),
                    )
                )
            midi.instruments.append(piano)
        midi.write(str(destination))
    except Exception as error:
        raise ScoreGenerationError("量化 MIDI 生成失败") from error


def write_musicxml(scored: "ScoredTranscription", destination: Path) -> None:
    try:
        scored.score.write("musicxml", fp=str(destination))
        read_musicxml_structure(destination)
    except Exception as error:
        raise ScoreGenerationError("MusicXML 生成失败") from error


def read_musicxml_visible_metadata(source: Path) -> dict[str, object]:
    root = ElementTree.parse(source).getroot()
    return {
        "work_title": root.findtext("./work/work-title"),
        "movement_title": root.findtext("./movement-title"),
        "composers": [
            (creator.text or "").strip()
            for creator in root.findall("./identification/creator")
            if creator.get("type") == "composer" and (creator.text or "").strip()
        ],
        "software": [
            (software.text or "").strip()
            for software in root.findall("./identification/encoding/software")
            if (software.text or "").strip()
        ],
    }


def read_musicxml_structure(source: Path) -> dict[str, object]:
    layout = read_musicxml_piano_layout(source)
    parsed = converter.parse(str(source))
    raise_for_structure_errors(parsed, validate_measure_durations=True)
    summary = score_structure_summary(parsed, validate_measure_durations=True)
    return {
        **summary,
        "part_count": layout["musicxml_part_count"],
        "measure_count": layout["measure_count"],
        "music21_staff_count": summary["part_count"],
        "staff_measure_count": summary["measure_count"],
        **layout,
    }


def read_musicxml_piano_layout(source: Path) -> dict[str, object]:
    root = ElementTree.parse(source).getroot()
    score_parts = root.findall("./part-list/score-part")
    parts = root.findall("./part")
    measures = parts[0].findall("./measure") if len(parts) == 1 else []
    first_measure = measures[0] if measures else None
    staves = first_measure.find("./attributes/staves") if first_measure is not None else None
    clefs = {
        item.get("number"): (item.findtext("./sign"), item.findtext("./line"))
        for item in (
            first_measure.findall("./attributes/clef") if first_measure is not None else []
        )
    }
    notes = parts[0].findall("./measure/note") if len(parts) == 1 else []
    note_staffs = [item.findall("./staff") for item in notes]
    staff_numbers = {staff[0].text for staff in note_staffs if len(staff) == 1 and staff[0].text}
    voices_by_staff: dict[str, set[str]] = {"1": set(), "2": set()}
    for notation, staffs in zip(notes, note_staffs, strict=True):
        if len(staffs) == 1 and staffs[0].text in voices_by_staff:
            voice = notation.findtext("./voice")
            if voice:
                voices_by_staff[staffs[0].text].add(voice)

    pedal_entries: list[tuple[str, str | None, str | None]] = []
    for direction in parts[0].findall("./measure/direction") if len(parts) == 1 else []:
        pedal = direction.find("./direction-type/pedal")
        if pedal is not None:
            pedal_entries.append(
                (pedal.get("number", "1"), pedal.get("type"), direction.findtext("./staff"))
            )

    errors: list[str] = []
    if len(score_parts) != 1:
        errors.append("EXPECTED_ONE_PIANO_SCORE_PART")
    if len(parts) != 1:
        errors.append("EXPECTED_ONE_PIANO_PART")
    score_part_id = score_parts[0].get("id") if len(score_parts) == 1 else None
    part_id = parts[0].get("id") if len(parts) == 1 else None
    if not score_part_id or score_part_id != part_id:
        errors.append("PIANO_PART_ID_MISMATCH")
    if len(score_parts) == 1 and (
        score_parts[0].findtext("./part-name") != "Piano"
        or score_parts[0].findtext("./score-instrument/instrument-name") != "Piano"
    ):
        errors.append("EXPECTED_PIANO_INSTRUMENT_NAME")
    if staves is None or staves.text != "2":
        errors.append("EXPECTED_TWO_PIANO_STAVES")
    if clefs != {"1": ("G", "2"), "2": ("F", "4")}:
        errors.append("EXPECTED_TREBLE_AND_BASS_CLEFS")
    if not notes or any(
        len(staffs) != 1 or staffs[0].text not in {"1", "2"} for staffs in note_staffs
    ):
        errors.append("INVALID_PIANO_NOTE_STAFF")
    if staff_numbers != {"1", "2"}:
        errors.append("EXPECTED_NUMBERED_PIANO_NOTES")
    if any(not measure.findall("./backup") for measure in measures):
        errors.append("EXPECTED_PIANO_STAFF_BACKUP")
    errors.extend(_pedal_mark_errors(pedal_entries))
    if errors:
        raise ValueError(", ".join(sorted(set(errors))))

    pedal_mark_count = sum(item[1] == "start" for item in pedal_entries)
    return {
        "musicxml_score_part_count": len(score_parts),
        "musicxml_part_count": len(parts),
        "staff_count": int(staves.text),
        "measure_count": len(measures),
        "clefs": {number: f"{value[0]}{value[1]}" for number, value in sorted(clefs.items())},
        "staff_numbers": sorted(staff_numbers),
        "voices_by_staff": {number: sorted(voices) for number, voices in voices_by_staff.items()},
        "backup_count": sum(len(measure.findall("./backup")) for measure in measures),
        "pedal_mark_count": pedal_mark_count,
    }


def _pedal_mark_errors(
    entries: list[tuple[str, str | None, str | None]],
) -> list[str]:
    errors = []
    open_marks: dict[str, str] = {}
    for number, action, staff in entries:
        if staff not in {"1", "2"}:
            errors.append("INVALID_PIANO_PEDAL_STAFF")
            continue
        if action == "start" and number not in open_marks:
            open_marks[number] = staff
        elif action == "stop" and open_marks.get(number) == staff:
            del open_marks[number]
        else:
            errors.append("INVALID_PIANO_PEDAL_MARK")
    if open_marks:
        errors.append("UNPAIRED_PIANO_PEDAL_MARK")
    return errors
