from xml.etree import ElementTree as ET


def read_single_piano_layout(root: ET.Element) -> dict[str, object]:
    """Validate the MusicXML single-staff branch, including later measures."""
    parts = root.findall("./part")
    definitions = root.findall("./part-list/score-part")
    if len(parts) != 1 or len(definitions) != 1:
        raise ValueError("EXPECTED_ONE_PIANO_PART")
    part, definition = parts[0], definitions[0]
    if not part.get("id") or part.get("id") != definition.get("id"):
        raise ValueError("PIANO_PART_ID_MISMATCH")
    if (
        definition.findtext("./part-name") != "Piano"
        or definition.findtext("./score-instrument/instrument-name") != "Piano"
    ):
        raise ValueError("EXPECTED_PIANO_INSTRUMENT_NAME")
    measures = part.findall("./measure")
    if not measures or not measures[0].findall("./attributes/clef"):
        raise ValueError("EXPECTED_SINGLE_TREBLE_CLEF")
    for item in part.findall("./measure/attributes/clef"):
        if (item.get("number", "1"), item.findtext("sign"), item.findtext("line")) != (
            "1",
            "G",
            "2",
        ):
            raise ValueError("EXPECTED_SINGLE_TREBLE_CLEF")
    if any(item.text != "1" for item in part.findall("./measure/attributes/staves")):
        raise ValueError("UNEXPECTED_STAFF_LAYOUT_CHANGE")
    notes = part.findall("./measure/note")
    if not notes or any(
        len(item.findall("staff")) > 1 or item.findtext("staff", "1") != "1" for item in notes
    ):
        raise ValueError("INVALID_PIANO_NOTE_STAFF")
    all_voices = {item.findtext("voice", "1") for item in notes}
    maximum = max(len({n.findtext("voice", "1") for n in m.findall("note")}) for m in measures)
    return {
        "musicxml_score_part_count": 1,
        "musicxml_part_count": 1,
        "staff_count": 1,
        "measure_count": len(measures),
        "clefs": {"1": "G2"},
        "staff_numbers": ["1"],
        "voices_by_staff": {"1": sorted(all_voices)},
        "maximum_voices_by_staff_measure": {"1": maximum},
        "backup_count": len(part.findall("./measure/backup")),
    }
