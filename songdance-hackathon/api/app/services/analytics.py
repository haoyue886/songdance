import hashlib
import hmac
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from sqlalchemy.orm import Session, sessionmaker

from app.models import AnalyticsEvent, TranscriptionJob
from app.observability import log_event
from app.settings import Settings

CLIENT_EVENT_PROPERTIES = {
    "result_viewed": {"view"},
    "view_changed": {"view"},
    "playback_started": {"mode"},
    "format_downloaded": {"format"},
}
ALLOWED_VIEWS = {"score", "roll"}
ALLOWED_PLAYBACK_MODES = {"source", "midi"}
ALLOWED_DOWNLOAD_FORMATS = {"midi", "musicxml", "pdf"}


def validate_client_event(event_name: str, properties: dict[str, object]) -> dict[str, object]:
    allowed = CLIENT_EVENT_PROPERTIES.get(event_name)
    if allowed is None or set(properties) - allowed:
        raise ValueError("Event name or properties are not allowed")
    view = properties.get("view")
    if view is not None and view not in ALLOWED_VIEWS:
        raise ValueError("Event property value is not allowed")
    mode = properties.get("mode")
    if mode is not None and mode not in ALLOWED_PLAYBACK_MODES:
        raise ValueError("Event property value is not allowed")
    download_format = properties.get("format")
    if download_format is not None and download_format not in ALLOWED_DOWNLOAD_FORMATS:
        raise ValueError("Event property value is not allowed")
    return properties


def record_event(
    session: Session,
    settings: Settings,
    event_name: str,
    *,
    job_id: str | None = None,
    properties: dict[str, object] | None = None,
) -> None:
    session.add(
        AnalyticsEvent(
            id=secrets.token_urlsafe(24),
            event_name=event_name,
            job_id_hash=hash_job_id(job_id, settings) if job_id else None,
            properties=json.dumps(properties or {}, ensure_ascii=True, separators=(",", ":")),
        )
    )


def record_terminal_event(factory: sessionmaker[Session], settings: Settings, job_id: str) -> None:
    try:
        with factory() as session:
            job = session.get(TranscriptionJob, job_id)
            if job is None:
                return
            if job.error_code in {"DELETE_REQUESTED", "DELETE_FAILED"}:
                return
            event_name = "job_succeeded" if job.status == "succeeded" else "job_failed"
            record_event(
                session,
                settings,
                event_name,
                job_id=job_id,
                properties={
                    "attempt_count": job.attempt_count,
                    "error_code": job.error_code,
                    "model_version": job.result.model_version if job.result else None,
                },
            )
            session.commit()
    except Exception:
        log_event("analytics_write_failed", event_name="job_terminal")


@contextmanager
def observe_stage(
    factory: sessionmaker[Session],
    settings: Settings,
    job_id: str,
    stage: str,
    *,
    model_version: str | None = None,
) -> Iterator[None]:
    started = perf_counter()
    status = "succeeded"
    error_code: str | None = None
    try:
        yield
    except Exception as error:
        status = "failed"
        code = getattr(error, "code", None)
        error_code = code if isinstance(code, str) else type(error).__name__
        raise
    finally:
        properties = {
            "stage": stage,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
            "status": status,
            "model_version": model_version,
            "error_code": error_code,
        }
        log_event("pipeline_stage", job_id_hash=hash_job_id(job_id, settings), **properties)
        try:
            with factory() as session:
                record_event(
                    session,
                    settings,
                    "pipeline_stage",
                    job_id=job_id,
                    properties=properties,
                )
                session.commit()
        except Exception:
            log_event("analytics_write_failed", event_name="pipeline_stage")


def hash_job_id(job_id: str, settings: Settings) -> str:
    secret = settings.download_signing_secret.get_secret_value().encode()
    return hmac.new(secret, job_id.encode(), hashlib.sha256).hexdigest()
