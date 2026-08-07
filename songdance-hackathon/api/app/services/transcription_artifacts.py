from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.pipeline.artifacts import ARTIFACT_TYPES, write_timeline
from app.pipeline.score import ScoredTranscription, write_musicxml, write_quantized_midi
from app.services.storage import ObjectStorage
from app.services.transcription_persistence import (
    DELETE_ERROR_CODES,
    ArtifactOutcome,
    locked_job,
)


def create_and_store_score_artifacts(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    job_id: str,
    attempt: int,
    paths: dict[str, Path],
    scored: ScoredTranscription,
    active_model_version: str,
    cleanup_summary: dict[str, object],
) -> list[ArtifactOutcome]:
    writers: dict[str, Callable[[], None]] = {
        "midi": lambda: write_quantized_midi(scored, paths["midi"]),
        "musicxml": lambda: write_musicxml(scored, paths["musicxml"]),
        "timeline": lambda: write_timeline(
            scored,
            paths["timeline"],
            model_version=active_model_version,
            cleanup_summary=cleanup_summary,
        ),
    }
    return [
        write_and_store_artifact(
            factory, storage, job_id, attempt, artifact_type, paths[artifact_type], writer
        )
        for artifact_type, writer in writers.items()
    ]


def write_and_store_artifact(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    job_id: str,
    attempt: int,
    artifact_type: str,
    path: Path,
    writer: Callable[[], None],
) -> ArtifactOutcome:
    filename, mime_type = ARTIFACT_TYPES[artifact_type]
    storage_key = artifact_storage_key(job_id, attempt, filename)
    try:
        writer()
        if not path.is_file() or path.stat().st_size == 0:
            raise OSError("artifact writer produced no data")
        size_bytes = path.stat().st_size
    except Exception:
        return ArtifactOutcome(
            artifact_type,
            "failed",
            None,
            mime_type,
            0,
            f"{artifact_type.upper()}_GENERATION_FAILED",
        )
    with factory() as session:
        job = locked_job(session, job_id)
        if (
            job is None
            or job.error_code in DELETE_ERROR_CODES
            or job.attempt_count != attempt
        ):
            return ArtifactOutcome(
                artifact_type, "failed", None, mime_type, 0, "JOB_UNAVAILABLE"
            )
        try:
            storage.put_file(storage_key, path, mime_type)
            session.commit()
        except Exception:
            return ArtifactOutcome(
                artifact_type,
                "failed",
                None,
                mime_type,
                0,
                f"{artifact_type.upper()}_STORAGE_FAILED",
            )
    return ArtifactOutcome(
        artifact_type, "succeeded", storage_key, mime_type, size_bytes, None
    )


def blocked_score_artifacts(error_code: str) -> list[ArtifactOutcome]:
    return [
        ArtifactOutcome(
            artifact_type,
            "failed",
            None,
            ARTIFACT_TYPES[artifact_type][1],
            0,
            error_code,
        )
        for artifact_type in ("midi", "musicxml", "timeline")
    ]


def artifact_storage_key(job_id: str, attempt: int, filename: str) -> str:
    return f"jobs/{job_id}/artifacts/attempt-{attempt}/{filename}"
