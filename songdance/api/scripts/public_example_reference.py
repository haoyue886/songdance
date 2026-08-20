import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from mido import MidiFile
from music21 import converter, key, meter

EXPECTED_PROVIDER = "IMSLP"
EXPECTED_SOURCE_URL = (
    "https://imslp.org/wiki/Piano_Sonata_No.16_in_C_major%2C_K.545_(Mozart%2C_Wolfgang_Amadeus)"
)
EXPECTED_DOWNLOAD_URL = "https://imslp.org/images/6/67/PMLP1855-sonata-in-c.mid"
EXPECTED_RIGHTS = "Public domain"
EXPECTED_REFERENCE_MEASURE_COUNT = 73
EXPECTED_AUDIO_MEASURE_COUNT = 17
EXPECTED_AUDIO_TEMPO_BPM = 136
EXPECTED_ALIGNMENT_METHOD = "fixed-clip-tempo-and-pitch-class-window"
EXPECTED_ALIGNMENT_EVIDENCE_SHA256 = (
    "51934c8bb8e72d74dc7e8bddd3b5943bbedf2e7a00887d9a69720cc251fea76f"
)


def validate_reference_contract(
    contract_path: Path,
    case_id: str,
    source_audio: Path,
    source_metadata: dict[str, object],
    timeline: dict[str, object],
    generated_score_path: Path,
) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    _validate_audio_binding(contract, case_id, source_audio, source_metadata)
    reference = _validate_reference_score(contract, contract_path)
    _validate_timeline(contract, timeline)
    mapping = _validate_audio_reference_mapping(contract, timeline, generated_score_path, reference)
    _validate_generated_score(reference, generated_score_path)
    return {
        "status": "passed",
        "contract_schema_version": contract["schema_version"],
        "contract_sha256": _file_sha256(contract_path),
        "provider": reference["provider"],
        "source_url": reference["source_url"],
        "download_url": reference["download_url"],
        "reference_format": reference["format"],
        "reference_score_sha256": reference["sha256"],
        "reference_measure_range": reference["measure_range"],
        "reference_measure_count": reference["measure_count"],
        "audio_reference_measure_count": len(mapping),
        "audio_reference_mapping": mapping,
        "notation_key_signature": reference["notation_key_signature"],
        "shortest_note_value": reference["shortest_note_value"],
        "divisions_per_quarter": reference["divisions_per_quarter"],
    }


def _validate_audio_binding(
    contract: dict[str, object],
    case_id: str,
    source_audio: Path,
    source_metadata: dict[str, object],
) -> None:
    binding = contract.get("audio_binding", {})
    expected = {
        "sha256": _file_sha256(source_audio),
        "clip_start_sec": source_metadata["start_sec"],
        "clip_duration_sec": source_metadata["duration_seconds"],
        "source_page": source_metadata["source_page"],
    }
    if contract.get("case_id") != case_id or any(
        binding.get(field) != value for field, value in expected.items()
    ):
        raise ValueError("public example reference contract is not bound to the source clip")


def _validate_reference_score(
    contract: dict[str, object], contract_path: Path
) -> dict[str, object]:
    if contract.get("schema_version") != 2:
        raise ValueError("public example reference contract schema is stale")
    reference = contract.get("reference_score", {})
    required = ("format", "path", "provider", "source_url", "download_url", "sha256")
    if any(not isinstance(reference.get(field), str) for field in required):
        raise ValueError("public example reference score metadata is incomplete")
    if (
        reference["format"] != "midi"
        or reference["provider"] != EXPECTED_PROVIDER
        or reference["source_url"] != EXPECTED_SOURCE_URL
        or reference["download_url"] != EXPECTED_DOWNLOAD_URL
        or reference.get("composition_rights") != EXPECTED_RIGHTS
    ):
        raise ValueError("public example reference source metadata is not trusted")
    relative_path = Path(reference["path"])
    if relative_path.is_absolute() or relative_path.parent != Path("."):
        raise ValueError("public example reference MIDI path must stay beside the contract")
    score_path = (contract_path.parent / relative_path).resolve()
    if not score_path.is_file() or _file_sha256(score_path) != reference["sha256"]:
        raise ValueError("public example reference MIDI fingerprint mismatch")

    midi = MidiFile(str(score_path))
    if midi.type != 1 or midi.ticks_per_beat != 480:
        raise ValueError("public example reference MIDI format is invalid")
    score = converter.parse(score_path)
    parts = list(score.parts)
    measures_by_part = [list(part.getElementsByClass("Measure")) for part in parts]
    if len(parts) != 2 or any(
        len(measures) != EXPECTED_REFERENCE_MEASURE_COUNT for measures in measures_by_part
    ):
        raise ValueError("public example reference MIDI does not cover 73 piano measures")
    if any(
        [measure.number for measure in measures]
        != list(range(1, EXPECTED_REFERENCE_MEASURE_COUNT + 1))
        for measures in measures_by_part
    ):
        raise ValueError("public example reference MIDI measure numbering is invalid")
    key_names = {
        signature.asKey().name for signature in score.recurse().getElementsByClass(key.KeySignature)
    }
    fifths = {
        signature.sharps for signature in score.recurse().getElementsByClass(key.KeySignature)
    }
    time_signatures = {
        signature.ratioString
        for signature in score.recurse().getElementsByClass(meter.TimeSignature)
    }
    note_type_counts = Counter(item.duration.type for item in score.recurse().notes)
    measure_range = reference.get("measure_range")
    if (
        measure_range != [1, EXPECTED_REFERENCE_MEASURE_COUNT]
        or reference.get("measure_count") != EXPECTED_REFERENCE_MEASURE_COUNT
    ):
        raise ValueError("public example reference measure range is incomplete")
    first_measure, last_measure = measure_range
    measure_minima = [
        min(
            float(item.duration.quarterLength)
            for part in parts
            for item in part.measure(measure_number).recurse().notes
        )
        for measure_number in range(first_measure, last_measure + 1)
    ]
    expected_counts = reference.get("note_type_counts")
    if (
        key_names != {reference.get("notation_key_signature")}
        or fifths != {reference.get("key_signature_fifths")}
        or time_signatures != {reference.get("time_signature")}
        or dict(note_type_counts) != expected_counts
        or measure_minima != reference.get("measure_shortest_quarter_lengths")
        or min(measure_minima) != 0.25
        or reference.get("shortest_note_value") != 16
        or reference.get("divisions_per_quarter") != 4
        or reference.get("midi_resolution") != midi.ticks_per_beat
    ):
        raise ValueError("public example reference score truth does not match the fixed MIDI")
    return reference


def _validate_audio_reference_mapping(
    contract: dict[str, object],
    timeline: dict[str, object],
    generated_score_path: Path,
    reference: dict[str, object],
) -> list[dict[str, int]]:
    mapping_data = contract.get("audio_reference_mapping", {})
    mapping = mapping_data.get("mapping")
    expected_count = mapping_data.get("audio_measure_count")
    if (
        mapping_data.get("schema_version") != 1
        or expected_count != EXPECTED_AUDIO_MEASURE_COUNT
        or not isinstance(mapping, list)
    ):
        raise ValueError("public example audio reference mapping is incomplete")
    if len(mapping) != expected_count or mapping_data.get("reference_measure_range") != [
        1,
        expected_count,
    ]:
        raise ValueError("public example audio reference mapping count is invalid")
    normalized: list[dict[str, int]] = []
    for index, item in enumerate(mapping, start=1):
        if (
            not isinstance(item, dict)
            or item.get("audio_measure_index") != index
            or item.get("reference_measure_number") != index
        ):
            raise ValueError("public example audio reference mapping is not ordered")
        normalized.append({"audio_measure_index": index, "reference_measure_number": index})
    if (
        len(timeline.get("downbeat_grid_seconds", [])) != expected_count
        or len(timeline.get("analysis", {}).get("downbeat_grid_seconds", [])) != expected_count
    ):
        raise ValueError("public example timeline does not cover the mapped audio measures")
    root = ElementTree.parse(generated_score_path).getroot()
    measure_count = len(root.findall("./part/measure"))
    if (
        measure_count != expected_count
        or reference.get("measure_count") != EXPECTED_REFERENCE_MEASURE_COUNT
    ):
        raise ValueError("public example generated score does not cover the mapped measures")
    evidence = mapping_data.get("alignment_evidence", {})
    pitch_similarity = (
        evidence.get("pitch_class_cosine_by_measure") if isinstance(evidence, dict) else None
    )
    if (
        not isinstance(evidence, dict)
        or hashlib.sha256(
            json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        != EXPECTED_ALIGNMENT_EVIDENCE_SHA256
        or evidence.get("method") != EXPECTED_ALIGNMENT_METHOD
        or evidence.get("audio_origin_sec") != 0.0
        or evidence.get("audio_duration_sec")
        != contract.get("audio_binding", {}).get("clip_duration_sec")
        or evidence.get("tempo_bpm") != EXPECTED_AUDIO_TEMPO_BPM
        or evidence.get("audio_downbeat_count") != expected_count
        or evidence.get("audio_quarter_length_estimate") != expected_count * 4.0
        or evidence.get("reference_window_quarter_length") != expected_count * 4.0
        or evidence.get("time_signature") != reference.get("time_signature")
        or not isinstance(pitch_similarity, list)
        or len(pitch_similarity) != expected_count
        or any(
            not isinstance(value, (int, float)) or not 0 <= value <= 1 for value in pitch_similarity
        )
    ):
        raise ValueError("public example audio reference alignment evidence is incomplete")
    return normalized


def _validate_timeline(contract: dict[str, object], timeline: dict[str, object]) -> None:
    expected = contract.get("expected_transcription", {})
    notation = timeline.get("notation", {})
    quantization = timeline.get("quantization", {})
    reconstruction = timeline.get("reconstruction", {})
    reconstruction_notation = reconstruction.get("notation", {})
    reconstruction_quantization = reconstruction.get("quantization", {})
    expected_key = expected.get("notation_key_signature")
    expected_key_source = expected.get("notation_key_signature_source")
    expected_divisions = expected.get("quantization_divisions_per_quarter")
    expected_shortest = expected.get("shortest_note_value")
    expected_quantization_source = expected.get("quantization_source")
    key_views = [
        (timeline.get("key_signature"), expected_key_source),
        (timeline.get("notation_key_signature"), expected_key_source),
        (notation.get("notation_key_signature"), notation.get("notation_key_signature_source")),
        (
            reconstruction_notation.get("notation_key_signature"),
            reconstruction_notation.get("notation_key_signature_source"),
        ),
    ]
    quantization_views = [quantization, reconstruction_quantization]
    if any(
        key_value != expected_key or key_source != expected_key_source
        for key_value, key_source in key_views
    ) or any(
        view.get("divisions_per_quarter") != expected_divisions
        or view.get("shortest_note_value") != expected_shortest
        or view.get("source") != expected_quantization_source
        for view in quantization_views
    ):
        raise ValueError("public example timeline does not match the reference score truth")


def _validate_generated_score(reference: dict[str, object], score_path: Path) -> None:
    root = ElementTree.parse(score_path).getroot()
    fifths = {
        int(element.text)
        for element in root.findall("./part/measure/attributes/key/fifths")
        if element.text is not None
    }
    note_types = {
        element.text
        for element in root.findall("./part/measure/note/type")
        if element.text is not None
    }
    shortest_value = max(
        (_NOTE_TYPE_VALUES.get(note_type, 0) for note_type in note_types), default=0
    )
    if (
        fifths != {reference.get("key_signature_fifths")}
        or shortest_value != reference.get("shortest_note_value")
        or "16th" not in note_types
    ):
        raise ValueError("public example MusicXML does not match the reference score truth")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_NOTE_TYPE_VALUES = dict(
    zip(
        ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "128th"),
        (1, 2, 4, 8, 16, 32, 64, 128),
        strict=True,
    )
)
