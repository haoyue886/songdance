import json
from dataclasses import asdict
from pathlib import Path

from app.pipeline.quality import _event_sort_key, pipeline_postprocess_version
from app.pipeline.score import ScoredTranscription
from app.pipeline.transcribe import MODEL_VERSION, NoteEvent

ARTIFACT_TYPES = {
    "raw_midi": ("raw.mid", "audio/midi"),
    "raw_timeline": ("raw-timeline.json", "application/json"),
    "midi": ("score.mid", "audio/midi"),
    "musicxml": ("score.musicxml", "application/vnd.recordare.musicxml+xml"),
    "timeline": ("timeline.json", "application/json"),
}


def artifact_paths(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {kind: output_dir / config[0] for kind, config in ARTIFACT_TYPES.items()}


def write_timeline(
    scored: ScoredTranscription,
    destination: Path,
    *,
    model_version: str = MODEL_VERSION,
    cleanup_summary: dict[str, object] | None = None,
) -> None:
    timeline = {
        "schema_version": 1,
        "model_version": model_version,
        "postprocess_version": pipeline_postprocess_version(
            cleanup_summary, scored.analysis.summary()
        ),
        "kind": "cleaned_note_events",
        "cleanup": cleanup_summary,
        "tempo_bpm": scored.tempo_bpm,
        "beat_grid_seconds": list(scored.analysis.beat_grid_seconds),
        "downbeat_grid_seconds": list(scored.analysis.downbeat_grid_seconds),
        "time_signature": scored.analysis.time_signature,
        "key_signature": scored.analysis.key_signature,
        "analysis": scored.analysis.summary(),
        "reconstruction": scored.reconstruction,
        "quality_flags": scored.quality_flags,
        "notes": [
            {"id": f"note-{index + 1}", **asdict(event)} for index, event in enumerate(scored.notes)
        ],
    }
    destination.write_text(
        json.dumps(timeline, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def write_raw_timeline(
    events: list[NoteEvent], destination: Path, *, model_version: str = MODEL_VERSION
) -> None:
    timeline = {
        "schema_version": 1,
        "model_version": model_version,
        "kind": "raw_model_events",
        "tempo_bpm": 120.0,
        "time_signature": "4/4",
        "quality_flags": ["RAW_MODEL_EVENTS"],
        "notes": [
            {"id": f"raw-note-{index + 1}", **asdict(event)}
            for index, event in enumerate(
                sorted(events, key=_event_sort_key)
            )
        ],
    }
    destination.write_text(
        json.dumps(timeline, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
