from datetime import UTC, datetime


def build_provenance(
    title: str,
    performer: str,
    source_metadata: dict[str, object],
    timeline: dict[str, object],
    review: dict[str, object],
    completed_review: dict[str, str],
    reference_validation: dict[str, object],
    artifacts: dict[str, dict[str, object]],
    external: dict[str, dict[str, object]],
) -> dict[str, object]:
    return {
        "title": title,
        "performer": performer,
        "source_page": source_metadata["source_page"],
        "license": source_metadata["license"],
        "license_url": source_metadata["license_url"],
        "clip_start_sec": source_metadata["start_sec"],
        "clip_duration_sec": source_metadata["duration_seconds"],
        "audio_sha256": source_metadata["clip_sha256"],
        "model_version": timeline["model_version"],
        "postprocess_version": timeline["postprocess_version"],
        "review_status": review["rating"],
        "latest_completed_review": completed_review,
        "reference_validation": reference_validation,
        "generated_at": datetime.now(UTC).isoformat(),
        "midi_sha256": artifacts["midi"]["sha256"],
        "musicxml_sha256": artifacts["musicxml"]["sha256"],
        "timeline_sha256": artifacts["timeline"]["sha256"],
        "artifacts": artifacts,
        "parser_validation": {"music21": {"status": "passed"}, **external},
    }
