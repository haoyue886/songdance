import logging
import tempfile
from dataclasses import replace
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.models import JobStage, JobStatus, TranscriptionJob
from app.pipeline.artifacts import ARTIFACT_TYPES, artifact_paths, write_raw_timeline
from app.pipeline.audio import preprocess_audio
from app.pipeline.cleanup import clean_note_events, failed_cleanup_summary
from app.pipeline.errors import NoteCleanupError, PipelineError
from app.pipeline.harmonics import extract_harmonic_evidence
from app.pipeline.quality import build_quality_report
from app.pipeline.score import build_score, read_musicxml_structure
from app.pipeline.sustain import extract_sustain_evidence
from app.pipeline.transcribe import model_version, transcribe_audio, write_raw_midi
from app.services.analytics import observe_stage
from app.services.storage import ObjectStorage
from app.services.transcription_analysis import analyze_with_fallback
from app.services.transcription_artifacts import (
    artifact_storage_key,
    blocked_score_artifacts,
    create_and_store_score_artifacts,
    write_and_store_artifact,
)
from app.services.transcription_persistence import (
    DELETE_ERROR_CODES,
    locked_job,
    mark_failed,
    persist_artifact_outcomes,
    persist_quality_report,
    persist_result,
    set_stage,
)
from app.settings import Settings

logger = logging.getLogger(__name__)


def run_transcription_job(
    job_id: str,
    settings: Settings,
    factory: sessionmaker[Session],
    storage: ObjectStorage, *, attempt: int | None = None,
) -> None:
    source = _source_key(factory, job_id, attempt)
    if source is None:
        return
    source_key, active_attempt = source
    active_model_version = model_version(
        settings.model_onset_threshold, settings.model_frame_threshold
    )
    cleanup_config = settings.note_cleanup_config
    analysis_config = settings.structure_analysis_config
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    try:
        if not _clear_previous_outputs(factory, storage, job_id, active_attempt):
            return
        with tempfile.TemporaryDirectory(
            prefix=f"pipeline-{job_id[:8]}-", dir=settings.temp_path
        ) as raw:
            workdir = Path(raw)
            source = workdir / "source.wav"
            normalized = workdir / "normalized.wav"
            storage.download_file(source_key, source)
            if not set_stage(
                factory,
                job_id,
                JobStatus.RUNNING,
                JobStage.PREPROCESSING,
                expected_attempt=active_attempt,
            ):
                return
            with observe_stage(factory, settings, job_id, "preprocessing"):
                preprocess_audio(source, normalized)

            if not set_stage(
                factory,
                job_id,
                JobStatus.RUNNING,
                JobStage.TRANSCRIBING,
                expected_attempt=active_attempt,
            ):
                return
            with observe_stage(
                factory, settings, job_id, "transcribing", model_version=active_model_version
            ):
                events, raw_midi = transcribe_audio(
                    normalized,
                    onset_threshold=settings.model_onset_threshold,
                    frame_threshold=settings.model_frame_threshold,
                )
                paths = artifact_paths(workdir / "artifacts")
                raw_outcome = write_and_store_artifact(
                    factory,
                    storage,
                    job_id,
                    active_attempt,
                    "raw_midi",
                    paths["raw_midi"],
                    lambda: write_raw_midi(raw_midi, paths["raw_midi"]),
                )
                raw_timeline_outcome = write_and_store_artifact(
                    factory,
                    storage,
                    job_id,
                    active_attempt,
                    "raw_timeline",
                    paths["raw_timeline"],
                    lambda: write_raw_timeline(
                        events, paths["raw_timeline"], model_version=active_model_version
                    ),
                )
            raw_outcomes = [raw_outcome, raw_timeline_outcome]
            if not persist_artifact_outcomes(
                factory, storage, job_id, raw_outcomes, expected_attempt=active_attempt
            ):
                return
            if raw_outcome.status == "failed" or raw_timeline_outcome.status == "failed":
                mark_failed(
                    factory,
                    job_id,
                    raw_outcome.error_code
                    or raw_timeline_outcome.error_code
                    or "RAW_ARTIFACT_GENERATION_FAILED",
                    "原始模型转录证据生成失败",
                    expected_attempt=active_attempt,
                )
                return

            if not set_stage(
                factory,
                job_id,
                JobStatus.RUNNING,
                JobStage.SCORE,
                expected_attempt=active_attempt,
            ):
                return
            with observe_stage(factory, settings, job_id, "score"):
                try:
                    cleanup_result = clean_note_events(
                        events,
                        cleanup_config,
                        harmonic_evidence=extract_harmonic_evidence(normalized, events),
                    )
                    cleaned_events = cleanup_result.events
                    cleanup_summary = cleanup_result.summary()
                    cleanup_flag = "NOTE_CLEANUP_APPLIED"
                except NoteCleanupError as error:
                    cleaned_events = events
                    cleanup_summary = failed_cleanup_summary(
                        cleanup_config, len(events), error.code
                    )
                    cleanup_flag = "NOTE_CLEANUP_FALLBACK"
                except Exception:
                    logger.exception("Unexpected note cleanup failure for job %s", job_id)
                    cleaned_events = events
                    cleanup_summary = failed_cleanup_summary(
                        cleanup_config,
                        len(events),
                        "NOTE_CLEANUP_UNEXPECTED_ERROR",
                    )
                    cleanup_flag = "NOTE_CLEANUP_FALLBACK"
                structure_analysis = analyze_with_fallback(normalized, analysis_config, job_id)
                sustain_evidence = extract_sustain_evidence(normalized, raw_midi)
                try:
                    scored = build_score(
                        cleaned_events,
                        analysis=structure_analysis,
                        sustain_evidence=sustain_evidence,
                    )
                    scored = replace(
                        scored,
                        quality_flags=[*scored.quality_flags, cleanup_flag],
                    )
                except PipelineError as error:
                    persist_artifact_outcomes(
                        factory,
                        storage,
                        job_id,
                        blocked_score_artifacts(error.code),
                        expected_attempt=active_attempt,
                    )
                    persist_quality_report(
                        factory,
                        job_id,
                        build_quality_report(
                            events,
                            None,
                            cleaned_events=cleaned_events,
                            cleanup_summary=cleanup_summary,
                            analysis_summary=structure_analysis.summary(),
                            model_version=active_model_version,
                            thresholds={
                                "onset": settings.model_onset_threshold,
                                "frame": settings.model_frame_threshold,
                            },
                            musicxml_status="failed",
                            musicxml_error_code=error.code,
                            structure_summary={"status": "not_evaluated", "errors": [error.code]},
                        ),
                        expected_attempt=active_attempt,
                    )
                    raise
                outcomes = create_and_store_score_artifacts(
                    factory,
                    storage,
                    job_id,
                    active_attempt,
                    paths,
                    scored,
                    active_model_version,
                    cleanup_summary,
                )
                musicxml_outcome = next(
                    outcome for outcome in outcomes if outcome.type == "musicxml"
                )
                musicxml_structure = (
                    read_musicxml_structure(paths["musicxml"])
                    if musicxml_outcome.status == "succeeded"
                    else None
                )
                persist_result(
                    factory,
                    storage,
                    job_id,
                    scored,
                    outcomes,
                    active_model_version,
                    build_quality_report(
                        events,
                        scored,
                        cleaned_events=cleaned_events,
                        cleanup_summary=cleanup_summary,
                        analysis_summary=structure_analysis.summary(),
                        model_version=active_model_version,
                        thresholds={
                            "onset": settings.model_onset_threshold,
                            "frame": settings.model_frame_threshold,
                        },
                        musicxml_status=(
                            "passed" if musicxml_outcome.status == "succeeded" else "failed"
                        ),
                        musicxml_error_code=musicxml_outcome.error_code,
                        structure_summary=musicxml_structure,
                    ),
                    expected_attempt=active_attempt,
                )
    except PipelineError as error:
        mark_failed(factory, job_id, error.code, error.message, expected_attempt=active_attempt)


def _source_key(
    factory: sessionmaker[Session], job_id: str, expected_attempt: int | None
) -> tuple[str, int] | None:
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
        return job.source_asset.storage_key, job.attempt_count


def _clear_previous_outputs(
    factory: sessionmaker[Session], storage: ObjectStorage, job_id: str, expected_attempt: int
) -> bool:
    with factory() as session:
        job = locked_job(session, job_id)
        if (
            job is None
            or job.error_code in DELETE_ERROR_CODES
            or job.attempt_count != expected_attempt
        ):
            return False
        keys = {
            artifact_storage_key(job_id, expected_attempt, filename)
            for filename, _mime_type in ARTIFACT_TYPES.values()
        }
        keys.update(artifact.storage_key for artifact in job.artifacts if artifact.storage_key)
        for artifact in list(job.artifacts):
            session.delete(artifact)
        if job.result is not None:
            session.delete(job.result)
        if job.quality_report is not None:
            session.delete(job.quality_report)
        session.commit()
    for key in sorted(keys):
        storage.delete(key)
    return True
