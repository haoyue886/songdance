import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event, Thread, current_thread

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue, SimpleWorker
from rq.job import Job
from sqlalchemy import event, select

from app.jobs.cleanup import cleanup_expired_jobs
from app.main import create_app
from app.models import AnalyticsEvent, JobStage, JobStatus, TranscriptionJob
from app.services.analytics import hash_job_id
from app.services.audio_validation import MAX_AUDIO_BYTES
from app.services.event_quota import EventQuotaExceeded
from app.services.queue import create_job_queue, queue_job_id
from app.services.quota import MemoryJobQuota, QuotaExceeded, RedisJobQuota
from app.services.storage import LocalObjectStorage, S3ObjectStorage, create_storage
from app.services.transcription_persistence import (
    ArtifactOutcome,
    persist_artifact_outcomes,
    set_stage,
)
from app.settings import Settings, get_settings
from tests.conftest import RecordingQueue, wav_bytes
from tests.test_jobs import create_job

INTEGRATION_DATABASE_URL = os.getenv("SONGDANCE_INTEGRATION_DATABASE_URL")
INTEGRATION_REDIS_URL = os.getenv("SONGDANCE_REDIS_URL")
INTEGRATION_S3_ENDPOINT_URL = os.getenv("SONGDANCE_S3_ENDPOINT_URL")


@pytest.mark.skipif(
    not INTEGRATION_S3_ENDPOINT_URL,
    reason="Set SONGDANCE_S3_ENDPOINT_URL for multipart cleanup test",
)
def test_s3_delete_aborts_only_exact_key_incomplete_multipart_uploads() -> None:
    settings = Settings(
        environment="test",
        storage_backend="s3",
        s3_endpoint_url=INTEGRATION_S3_ENDPOINT_URL,
        s3_bucket=os.environ["SONGDANCE_S3_BUCKET"],
        s3_access_key=os.environ["SONGDANCE_S3_ACCESS_KEY"],
        s3_secret_key=os.environ["SONGDANCE_S3_SECRET_KEY"],
    )
    storage = S3ObjectStorage(settings)
    storage.ensure_ready()
    key = "phase6-tests/incomplete-source.wav"
    neighbor_key = f"{key}-neighbor"
    storage.delete(key)
    storage.delete(neighbor_key)
    target = storage.client.create_multipart_upload(Bucket=storage.bucket, Key=key)
    neighbor = storage.client.create_multipart_upload(Bucket=storage.bucket, Key=neighbor_key)
    storage.client.upload_part(
        Bucket=storage.bucket,
        Key=key,
        UploadId=target["UploadId"],
        PartNumber=1,
        Body=b"private audio part",
    )
    storage.client.upload_part(
        Bucket=storage.bucket,
        Key=neighbor_key,
        UploadId=neighbor["UploadId"],
        PartNumber=1,
        Body=b"neighbor private audio part",
    )
    try:
        storage.delete(key)
        target_uploads = storage.client.list_multipart_uploads(
            Bucket=storage.bucket,
            Prefix=key,
        ).get("Uploads", [])
        neighbor_uploads = storage.client.list_multipart_uploads(
            Bucket=storage.bucket,
            Prefix=neighbor_key,
        ).get("Uploads", [])

        assert all(upload["UploadId"] != target["UploadId"] for upload in target_uploads)
        assert any(upload["UploadId"] == neighbor["UploadId"] for upload in neighbor_uploads)
    finally:
        storage.delete(key)
        storage.delete(neighbor_key)


@pytest.mark.skipif(
    not INTEGRATION_REDIS_URL,
    reason="Set SONGDANCE_REDIS_URL for Redis quota test",
)
def test_redis_quota_is_atomic_and_releases_only_active_capacity() -> None:
    settings = Settings(
        environment="test",
        redis_url=INTEGRATION_REDIS_URL or "redis://localhost:6379/0",
        quota_namespace="phase6-contract",
        hourly_job_limit=10,
        client_active_job_limit=2,
        global_active_job_limit=2,
        daily_job_limit=2,
    )
    redis = Redis.from_url(str(settings.redis_url))
    keys = list(redis.scan_iter("songdance:phase6-contract:*"))
    if keys:
        redis.delete(*keys)
    quota = RedisJobQuota(settings)
    quota.reserve("job-a", "client-a")
    quota.reserve("job-b", "client-b")
    with pytest.raises(QuotaExceeded) as global_error:
        quota.reserve("job-c", "client-c")
    assert global_error.value.code == "GLOBAL_CAPACITY"
    quota.complete("job-a")
    quota.complete("job-b")
    with pytest.raises(QuotaExceeded) as daily_error:
        quota.reserve("job-c", "client-c")
    assert daily_error.value.code == "DAILY_CAPACITY"
    keys = list(redis.scan_iter("songdance:phase6-contract:*"))
    if keys:
        redis.delete(*keys)


@pytest.mark.skipif(
    not INTEGRATION_REDIS_URL,
    reason="Set SONGDANCE_REDIS_URL for Redis event quota test",
)
def test_redis_event_quota_atomically_caps_concurrent_writes() -> None:
    settings = Settings(
        environment="test",
        redis_url=INTEGRATION_REDIS_URL or "redis://localhost:6379/0",
        quota_namespace="phase6-event-contract",
        analytics_job_event_limit_per_minute=10,
        analytics_client_event_limit_per_minute=20,
        analytics_global_event_limit_per_minute=20,
    )
    redis = Redis.from_url(str(settings.redis_url))
    keys = list(redis.scan_iter("songdance:phase6-event-contract:*"))
    if keys:
        redis.delete(*keys)
    quota = RedisJobQuota(settings)

    def reserve() -> bool:
        try:
            quota.reserve_event("job-a", "client-a")
            return True
        except EventQuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=20) as pool:
        accepted = list(pool.map(lambda _index: reserve(), range(20)))

    assert accepted.count(True) == 10
    assert accepted.count(False) == 10
    keys = list(redis.scan_iter("songdance:phase6-event-contract:*"))
    if keys:
        redis.delete(*keys)


@pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="Set SONGDANCE_INTEGRATION_DATABASE_URL for PostgreSQL lock test",
)
def test_delete_failure_wins_over_concurrent_worker_stage_commit(tmp_path) -> None:
    settings = Settings(
        environment="test",
        database_url=INTEGRATION_DATABASE_URL or "",
        quota_backend="memory",
        storage_backend="local",
        local_storage_path=tmp_path / "storage",
        temp_path=tmp_path / "tmp",
        auto_create_schema=False,
        hourly_job_limit=100,
        client_active_job_limit=100,
        global_active_job_limit=100,
        daily_job_limit=1000,
        max_request_bytes=MAX_AUDIO_BYTES + 1024 * 1024,
    )
    storage = FailingDeleteStorage(settings.local_storage_path)
    app = create_app(
        settings=settings,
        storage=storage,
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )
    worker_before_commit = Event()
    release_worker = Event()

    def pause_stale_worker_update(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        if current_thread().name == "stale-worker" and statement.lstrip().startswith(
            "UPDATE transcription_jobs"
        ):
            worker_before_commit.set()
            assert release_worker.wait(timeout=5)

    event.listen(app.state.engine, "before_cursor_execute", pause_stale_worker_update)
    try:
        with TestClient(app) as client:
            job_id = create_job(client).json()["id"]
            worker = Thread(
                target=set_stage,
                args=(app.state.session_factory, job_id, JobStatus.SUCCEEDED, JobStage.COMPLETED),
                name="stale-worker",
            )
            deletion_status: list[int] = []
            worker.start()
            assert worker_before_commit.wait(timeout=5)

            deletion = Thread(
                target=lambda: deletion_status.append(client.delete(f"/jobs/{job_id}").status_code)
            )
            deletion.start()
            storage.delete_attempted.wait(timeout=1)
            release_worker.set()
            worker.join(timeout=5)
            deletion.join(timeout=5)

            assert not worker.is_alive() and not deletion.is_alive()
            assert deletion_status == [503]
            with app.state.session_factory() as session:
                job = session.get(TranscriptionJob, job_id)
                assert job is not None
                assert job.status == JobStatus.FAILED
                assert job.error_code == "DELETE_FAILED"
                session.delete(job)
                session.commit()
    finally:
        release_worker.set()
        event.remove(app.state.engine, "before_cursor_execute", pause_stale_worker_update)
        app.state.engine.dispose()


@pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="Set SONGDANCE_INTEGRATION_DATABASE_URL for PostgreSQL cleanup lock test",
)
def test_cleanup_lock_discards_worker_upload_after_object_sweep(tmp_path) -> None:
    settings = Settings(
        environment="test",
        database_url=INTEGRATION_DATABASE_URL or "",
        quota_backend="memory",
        storage_backend="local",
        local_storage_path=tmp_path / "storage",
        temp_path=tmp_path / "tmp",
        auto_create_schema=False,
        hourly_job_limit=100,
        client_active_job_limit=100,
        global_active_job_limit=100,
        daily_job_limit=1000,
    )
    storage = PausingCleanupStorage(settings.local_storage_path)
    app = create_app(
        settings=settings,
        storage=storage,
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )
    try:
        with TestClient(app) as client:
            job_id = create_job(client).json()["id"]
            with app.state.session_factory() as session:
                job = session.get(TranscriptionJob, job_id)
                assert job is not None
                job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                session.commit()

            cleanup_results = []
            cleanup = Thread(
                target=lambda: cleanup_results.append(
                    cleanup_expired_jobs(app.state.session_factory, storage, settings)
                )
            )
            cleanup.start()
            assert storage.sweep_finished.wait(timeout=5)

            artifact_key = f"jobs/{job_id}/artifacts/score.mid"
            artifact_file = tmp_path / "late-score.mid"
            artifact_file.write_bytes(b"MThd-late")
            worker_results: list[bool] = []

            def persist_late_upload() -> None:
                storage.put_file(artifact_key, artifact_file, "audio/midi")
                storage.worker_uploaded.set()
                worker_results.append(
                    persist_artifact_outcomes(
                        app.state.session_factory,
                        storage,
                        job_id,
                        [
                            ArtifactOutcome(
                                "midi",
                                "succeeded",
                                artifact_key,
                                "audio/midi",
                                artifact_file.stat().st_size,
                                None,
                            )
                        ],
                    )
                )

            worker = Thread(target=persist_late_upload)
            worker.start()
            assert storage.worker_uploaded.wait(timeout=5)
            storage.release_cleanup.set()
            cleanup.join(timeout=5)
            worker.join(timeout=5)

            assert not cleanup.is_alive() and not worker.is_alive()
            assert len(cleanup_results) == 1
            assert cleanup_results[0].deleted == 1
            assert worker_results == [False]
            assert not storage.exists(artifact_key)
            with app.state.session_factory() as session:
                assert session.get(TranscriptionJob, job_id) is None
    finally:
        storage.release_cleanup.set()
        app.state.engine.dispose()


class FailingDeleteStorage(LocalObjectStorage):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.delete_attempted = Event()

    def delete(self, key: str) -> None:
        self.delete_attempted.set()
        raise ConnectionError("storage unavailable")


class PausingCleanupStorage(LocalObjectStorage):
    def __init__(self, root) -> None:
        super().__init__(root)
        self.sweep_finished = Event()
        self.release_cleanup = Event()
        self.worker_uploaded = Event()

    def delete(self, key: str) -> None:
        super().delete(key)
        if key.endswith("timeline.json") and not self.sweep_finished.is_set():
            self.sweep_finished.set()
            assert self.release_cleanup.wait(timeout=5)


@pytest.mark.skipif(
    not INTEGRATION_DATABASE_URL,
    reason="Set SONGDANCE_INTEGRATION_DATABASE_URL to run real service integration",
)
def test_postgres_redis_minio_job_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        environment="test",
        database_url=INTEGRATION_DATABASE_URL or "",
        redis_url=os.environ["SONGDANCE_REDIS_URL"],
        queue_name="songdance-phase4-integration",
        quota_namespace="phase6-lifecycle",
        hourly_job_limit=10,
        storage_backend="s3",
        s3_endpoint_url=os.environ["SONGDANCE_S3_ENDPOINT_URL"],
        s3_bucket=os.environ["SONGDANCE_S3_BUCKET"],
        s3_access_key=os.environ["SONGDANCE_S3_ACCESS_KEY"],
        s3_secret_key=os.environ["SONGDANCE_S3_SECRET_KEY"],
        auto_create_schema=False,
    )
    get_settings.cache_clear()
    for name, value in {
        "SONGDANCE_ENVIRONMENT": "test",
        "SONGDANCE_DATABASE_URL": settings.database_url,
        "SONGDANCE_REDIS_URL": str(settings.redis_url),
        "SONGDANCE_QUEUE_NAME": settings.queue_name,
        "SONGDANCE_QUOTA_NAMESPACE": settings.quota_namespace,
        "SONGDANCE_QUOTA_BACKEND": "redis",
        "SONGDANCE_STORAGE_BACKEND": "s3",
        "SONGDANCE_S3_ENDPOINT_URL": settings.s3_endpoint_url or "",
        "SONGDANCE_S3_BUCKET": settings.s3_bucket,
        "SONGDANCE_S3_ACCESS_KEY": settings.s3_access_key or "",
        "SONGDANCE_S3_SECRET_KEY": settings.s3_secret_key.get_secret_value()
        if settings.s3_secret_key
        else "",
    }.items():
        os.environ[name] = value

    redis = Redis.from_url(str(settings.redis_url))
    quota_keys = list(redis.scan_iter("songdance:phase6-lifecycle:*"))
    if quota_keys:
        redis.delete(*quota_keys)
    queue = Queue(settings.queue_name, connection=redis)
    queue.empty()
    storage = create_storage(settings)
    app = create_app(
        settings=settings,
        storage=storage,
        job_queue=create_job_queue(settings),
    )

    with TestClient(app) as client:
        created = client.post(
            "/jobs",
            data={"start_sec": "0", "end_sec": "1.5", "rights_confirmed": "true"},
            files={
                "audio_file": (
                    "piano.wav",
                    wav_bytes(duration=2, sample_rate=22_050, frequency=440),
                    "audio/wav",
                )
            },
        )
        assert created.status_code == 201
        job_id = created.json()["id"]
        source_key = f"jobs/{job_id}/source.wav"
        assert storage.exists(source_key)
        assert queue.count == 1

        worker = SimpleWorker([queue], connection=redis)
        worker.work(burst=True, with_scheduler=False)
        assert redis.zcard("songdance:phase6-lifecycle:active:global") == 0
        assert queue.count == 0
        rq_job = Job.fetch(queue_job_id(job_id, 1, settings), connection=redis)
        assert rq_job.retries_left == 2
        assert rq_job.meta["worker_execution_count"] == 1
        queried = client.get(f"/jobs/{job_id}")
        assert queried.status_code == 200
        assert queried.json()["status"] == "succeeded"
        assert all(item["status"] == "succeeded" for item in queried.json()["artifacts"])
        midi_ticket = client.get(f"/jobs/{job_id}/download-url/midi")
        assert midi_ticket.status_code == 200
        midi_download = client.get(midi_ticket.json()["path"])
        assert midi_download.status_code == 200
        assert midi_download.content[:4] == b"MThd"

        deleted = client.delete(f"/jobs/{job_id}")
        assert deleted.status_code == 204
        assert not storage.exists(source_key)
        assert client.get(f"/jobs/{job_id}").status_code == 404

        failed_created = client.post(
            "/jobs",
            data={"start_sec": "0", "end_sec": "1.5", "rights_confirmed": "true"},
            files={"audio_file": ("failure.wav", wav_bytes(), "audio/wav")},
        )
        failed_job_id = failed_created.json()["id"]
        failed_source_key = f"jobs/{failed_job_id}/source.wav"

        def crash_worker(*_args, **_kwargs) -> None:
            raise ConnectionError("transient dependency failure")

        monkeypatch.setattr("app.jobs.tasks.run_transcription_job", crash_worker)
        SimpleWorker([queue], connection=redis).work(burst=True, with_scheduler=False)
        failed_rq_job = Job.fetch(queue_job_id(failed_job_id, 1, settings), connection=redis)
        assert failed_rq_job.retries_left == 0
        assert failed_rq_job.meta["worker_execution_count"] == 3
        failed_query = client.get(f"/jobs/{failed_job_id}")
        assert failed_query.json()["status"] == "failed"
        assert failed_query.json()["error_code"] == "WORKER_FAILED"
        with app.state.session_factory() as session:
            failure_event = session.scalar(
                select(AnalyticsEvent).where(
                    AnalyticsEvent.event_name == "job_failed",
                    AnalyticsEvent.job_id_hash == hash_job_id(failed_job_id, settings),
                )
            )
            assert failure_event is not None
            assert "WORKER_FAILED" in failure_event.properties
        assert redis.zcard("songdance:phase6-lifecycle:active:global") == 0
        monkeypatch.undo()

        retried = client.post(f"/jobs/{failed_job_id}/retry")
        assert retried.status_code == 200
        assert retried.json()["attempt_count"] == 2
        assert queue.count == 1
        queue.empty()

        failed_deleted = client.delete(f"/jobs/{failed_job_id}")
        assert failed_deleted.status_code == 204
        assert not storage.exists(failed_source_key)

        cleanup_created = client.post(
            "/jobs",
            data={"start_sec": "0", "end_sec": "1.5", "rights_confirmed": "true"},
            files={"audio_file": ("cleanup.wav", wav_bytes(), "audio/wav")},
        )
        assert cleanup_created.status_code == 201
        cleanup_job_id = cleanup_created.json()["id"]
        cleanup_source_key = f"jobs/{cleanup_job_id}/source.wav"
        with app.state.session_factory() as session:
            cleanup_job = session.get(TranscriptionJob, cleanup_job_id)
            assert cleanup_job is not None
            cleanup_job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            session.commit()
        cleaned = cleanup_expired_jobs(
            app.state.session_factory,
            storage,
            settings,
        )
        assert cleaned.deleted == 1 and cleaned.failed == 0
        assert not storage.exists(cleanup_source_key)
        with app.state.session_factory() as session:
            assert session.get(TranscriptionJob, cleanup_job_id) is None

    app.state.engine.dispose()
    redis.delete(f"rq:queue:{settings.queue_name}")
    quota_keys = list(redis.scan_iter("songdance:phase6-lifecycle:*"))
    if quota_keys:
        redis.delete(*quota_keys)
    get_settings.cache_clear()
