from sqlalchemy.orm import Session

from app.models import JobStatus, TranscriptionJob
from app.services.storage import ObjectStorage

ARTIFACT_FILENAMES = (
    "raw.mid",
    "raw-timeline.json",
    "score.mid",
    "score.musicxml",
    "timeline.json",
)


def remove_failed_upload_intent(
    session: Session,
    storage: ObjectStorage,
    job_id: str,
    storage_key: str,
) -> None:
    try:
        storage.delete(storage_key)
    except Exception:
        job = session.get(TranscriptionJob, job_id)
        if job is not None:
            job.status = JobStatus.FAILED
            job.error_code = "DELETE_FAILED"
            job.error_message = "上传失败后的临时文件将由清理任务重试删除"
            session.commit()
        return
    job = session.get(TranscriptionJob, job_id)
    if job is not None:
        session.delete(job)
        session.commit()


def delete_job_objects(job: TranscriptionJob, storage: ObjectStorage) -> None:
    extra_keys = [
        artifact.storage_key for artifact in job.artifacts if artifact.storage_key is not None
    ]
    delete_known_job_objects(job.id, storage, extra_keys)


def delete_known_job_objects(
    job_id: str, storage: ObjectStorage, extra_keys: list[str] | None = None
) -> None:
    keys = [f"jobs/{job_id}/source.wav"]
    keys.extend(f"jobs/{job_id}/artifacts/{filename}" for filename in ARTIFACT_FILENAMES)
    keys.extend(extra_keys or [])
    for key in dict.fromkeys(keys):
        storage.delete(key)
