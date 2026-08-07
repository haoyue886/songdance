import json
import secrets
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Artifact,
    JobStage,
    JobStatus,
    TranscriptionJob,
    TranscriptionQualityReport,
    TranscriptionResult,
)
from app.pipeline.quality import QUALITY_REPORT_VERSION
from app.pipeline.score import ScoredTranscription
from app.pipeline.transcribe import MODEL_VERSION
from app.services.storage import ObjectStorage

CRITICAL_ARTIFACTS = {"raw_midi", "raw_timeline", "midi", "timeline"}
DELETE_ERROR_CODES = {"DELETE_REQUESTED", "DELETE_FAILED"}


@dataclass(frozen=True)
class ArtifactOutcome:
    type: str
    status: str
    storage_key: str | None
    mime_type: str | None
    size_bytes: int
    error_code: str | None


def locked_job(session: Session, job_id: str) -> TranscriptionJob | None:
    return session.scalar(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
    )


def set_stage(
    factory: sessionmaker[Session],
    job_id: str,
    status: JobStatus,
    stage: JobStage,
    *,
    expected_attempt: int | None = None,
) -> bool:
    with factory() as session:
        job = locked_job(session, job_id)
        if not _is_active_attempt(job, expected_attempt):
            return False
        job.status = status
        job.stage = stage
        job.error_code = None
        job.error_message = None
        session.commit()
        return True


def persist_artifact_outcomes(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    job_id: str,
    outcomes: list[ArtifactOutcome],
    *,
    expected_attempt: int | None = None,
) -> bool:
    with factory() as session:
        job = locked_job(session, job_id)
        if not _is_active_attempt(job, expected_attempt):
            discard_outcomes(storage, outcomes)
            return False
        _apply_artifact_outcomes(job, outcomes)
        session.commit()
        return True


def persist_result(
    factory: sessionmaker[Session],
    storage: ObjectStorage,
    job_id: str,
    scored: ScoredTranscription,
    outcomes: list[ArtifactOutcome],
    model_version: str = MODEL_VERSION,
    quality_report: dict[str, object] | None = None,
    *,
    expected_attempt: int | None = None,
) -> bool:
    failed = {outcome.type for outcome in outcomes if outcome.status == "failed"}
    flags = [*scored.quality_flags, *(f"{kind.upper()}_FAILED" for kind in sorted(failed))]
    with factory() as session:
        job = locked_job(session, job_id)
        if not _is_active_attempt(job, expected_attempt):
            discard_outcomes(storage, outcomes)
            return False
        _apply_artifact_outcomes(job, outcomes)
        job.result = TranscriptionResult(
            id=secrets.token_urlsafe(24),
            tempo=scored.tempo_bpm,
            time_signature="4/4",
            note_count=len(scored.notes),
            quality_flags=json.dumps(flags, separators=(",", ":")),
            model_version=model_version,
        )
        if quality_report is not None:
            job.quality_report = TranscriptionQualityReport(
                id=secrets.token_urlsafe(24),
                report_version=QUALITY_REPORT_VERSION,
                summary=json.dumps(quality_report, ensure_ascii=False, separators=(",", ":")),
            )
        critical_failures = [
            outcome
            for outcome in outcomes
            if outcome.type in CRITICAL_ARTIFACTS and outcome.status == "failed"
        ]
        critical_failed = bool(critical_failures)
        job.status = JobStatus.FAILED if critical_failed else JobStatus.SUCCEEDED
        job.stage = JobStage.SCORE if critical_failed else JobStage.COMPLETED
        job.error_code = critical_failures[0].error_code if critical_failed else None
        job.error_message = "关键转录产物处理失败" if critical_failed else None
        session.commit()
        return True


def persist_quality_report(
    factory: sessionmaker[Session],
    job_id: str,
    quality_report: dict[str, object],
    *,
    expected_attempt: int,
) -> bool:
    with factory() as session:
        job = locked_job(session, job_id)
        if not _is_active_attempt(job, expected_attempt):
            return False
        job.quality_report = TranscriptionQualityReport(
            id=secrets.token_urlsafe(24),
            report_version=QUALITY_REPORT_VERSION,
            summary=json.dumps(quality_report, ensure_ascii=False, separators=(",", ":")),
        )
        session.commit()
        return True


def mark_failed(
    factory: sessionmaker[Session],
    job_id: str,
    code: str,
    message: str,
    *,
    expected_attempt: int | None = None,
) -> None:
    with factory() as session:
        job = locked_job(session, job_id)
        if not _is_active_attempt(job, expected_attempt):
            return
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        session.commit()


def _is_active_attempt(job: TranscriptionJob | None, expected_attempt: int | None) -> bool:
    return (
        job is not None
        and job.error_code not in DELETE_ERROR_CODES
        and (expected_attempt is None or job.attempt_count == expected_attempt)
    )


def _apply_artifact_outcomes(job: TranscriptionJob, outcomes: list[ArtifactOutcome]) -> None:
    existing = {artifact.type: artifact for artifact in job.artifacts}
    for outcome in outcomes:
        artifact = existing.get(outcome.type)
        if artifact is None:
            artifact = Artifact(id=secrets.token_urlsafe(24), type=outcome.type)
            job.artifacts.append(artifact)
        artifact.status = outcome.status
        artifact.storage_key = outcome.storage_key
        artifact.mime_type = outcome.mime_type
        artifact.size_bytes = outcome.size_bytes
        artifact.error_code = outcome.error_code


def discard_outcomes(storage: ObjectStorage, outcomes: list[ArtifactOutcome]) -> None:
    for outcome in outcomes:
        if outcome.storage_key is not None:
            storage.delete(outcome.storage_key)
