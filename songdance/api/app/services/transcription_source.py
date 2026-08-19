from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.models import TranscriptionJob
from app.services.transcription_persistence import DELETE_ERROR_CODES, mark_failed


def source_details(
    factory: sessionmaker[Session], job_id: str, expected_attempt: int | None
) -> tuple[str, int, str] | None:
    with factory() as session:
        job = session.get(TranscriptionJob, job_id)
        if job is None or job.error_code in DELETE_ERROR_CODES:
            return None
        if job.source_asset is None:
            mark_failed(
                factory,
                job_id,
                "UPLOAD_MISSING",
                "上传的源文件不可用",
                expected_attempt=expected_attempt,
            )
            return None
        if expected_attempt is not None and job.attempt_count != expected_attempt:
            return None
        return (
            job.source_asset.storage_key,
            job.attempt_count,
            score_title(job.source_asset.original_filename),
        )


def score_title(original_filename: str | None) -> str:
    if original_filename:
        path = Path(original_filename)
        title = "" if not path.suffix and original_filename.startswith(".") else path.stem.strip()
        if title and title not in {".", ".."}:
            return title
    return "SongDance Transcription"
