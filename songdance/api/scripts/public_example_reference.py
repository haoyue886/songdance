import hashlib
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from music21 import converter, corpus, key


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
    reference = _validate_bundled_score(contract)
    _validate_timeline(contract, timeline)
    _validate_generated_score(reference, generated_score_path)
    return {
        "status": "passed",
        "contract_schema_version": contract["schema_version"],
        "contract_sha256": _file_sha256(contract_path),
        "corpus_identifier": reference["corpus_identifier"],
        "reference_score_sha256": reference["sha256"],
        "reference_measure_range": reference["measure_range"],
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


def _validate_bundled_score(contract: dict[str, object]) -> dict[str, object]:
    reference = contract.get("reference_score", {})
    identifier = reference.get("corpus_identifier")
    if not isinstance(identifier, str):
        raise ValueError("public example reference score identifier is missing")
    score_path = Path(corpus.getWork(identifier))
    if _file_sha256(score_path) != reference.get("sha256"):
        raise ValueError("public example reference score fingerprint mismatch")

    score = converter.parse(score_path)
    key_names = {
        signature.asKey().name
        for signature in score.recurse().getElementsByClass(key.KeySignature)
    }
    fifths = {
        signature.sharps
        for signature in score.recurse().getElementsByClass(key.KeySignature)
    }
    note_type_counts = Counter(item.duration.type for item in score.recurse().notes)
    measure_range = reference.get("measure_range")
    if not (
        isinstance(measure_range, list)
        and len(measure_range) == 2
        and all(isinstance(value, int) for value in measure_range)
    ):
        raise ValueError("public example reference measure range is invalid")
    first_measure, last_measure = measure_range
    measure_minima = [
        min(
            float(item.duration.quarterLength)
            for part in score.parts
            for item in part.measure(measure_number).recurse().notes
        )
        for measure_number in range(first_measure, last_measure + 1)
    ]
    expected_counts = reference.get("note_type_counts")
    if (
        key_names != {reference.get("notation_key_signature")}
        or fifths != {reference.get("key_signature_fifths")}
        or dict(note_type_counts) != expected_counts
        or measure_minima != reference.get("measure_shortest_quarter_lengths")
        or min(measure_minima) != 0.25
        or reference.get("shortest_note_value") != 16
        or reference.get("divisions_per_quarter") != 4
    ):
        raise ValueError("public example reference score truth does not match the bundled score")
    return reference


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
        (
            notation.get("notation_key_signature"),
            notation.get("notation_key_signature_source"),
        ),
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
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_NOTE_TYPE_VALUES = {
    "whole": 1,
    "half": 2,
    "quarter": 4,
    "eighth": 8,
    "16th": 16,
    "32nd": 32,
    "64th": 64,
    "128th": 128,
}
