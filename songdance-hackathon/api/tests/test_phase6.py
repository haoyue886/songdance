import asyncio
import io
import json
import logging
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.jobs.cleanup import cleanup_expired_jobs
from app.main import create_app
from app.middleware.request_size import RequestSizeLimitMiddleware
from app.models import AnalyticsEvent, TranscriptionJob
from app.observability import JsonFormatter, configure_logging, logger
from app.pipeline.errors import ModelInferenceError
from app.services.analytics import record_terminal_event
from app.services.event_quota import EventQuotaExceeded
from app.services.quota import MemoryJobQuota, QuotaExceeded, client_quota_key
from app.services.storage import LocalObjectStorage
from app.services.temp_cleanup import cleanup_stale_temp_files
from app.settings import Settings
from tests.conftest import RecordingQueue, wav_bytes
from tests.test_jobs import create_job
from tests.test_transcription_service import fake_transcription, run_service


@pytest.fixture
def strict_client(tmp_path: Path) -> Iterator[TestClient]:
    app = make_test_app(tmp_path)
    with TestClient(app) as client:
        yield client
    app.state.engine.dispose()


def make_test_app(tmp_path: Path, **overrides: object):
    values: dict[str, object] = {
        "environment": "test",
        "database_url": f"sqlite:///{tmp_path / 'jobs.sqlite3'}",
        "storage_backend": "local",
        "local_storage_path": tmp_path / "storage",
        "temp_path": tmp_path / "tmp",
        "auto_create_schema": True,
    }
    values.update(overrides)
    settings = Settings(**values)
    storage = LocalObjectStorage(settings.local_storage_path)
    return create_app(
        settings=settings,
        storage=storage,
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )


def quota_request(forwarded_for: str) -> Request:
    return Request(
        {
            "type": "http",
            "client": ("10.0.0.8", 1234),
            "headers": [(b"x-forwarded-for", forwarded_for.encode())],
        }
    )


def test_proxy_hops_ignore_attacker_prepended_forwarded_addresses() -> None:
    settings = Settings(
        environment="test",
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="10.0.0.0/8",
    )

    original = client_quota_key(quota_request("198.51.100.20"), settings)
    spoofed = client_quota_key(quota_request("203.0.113.9, 198.51.100.20"), settings)
    other_client = client_quota_key(quota_request("203.0.113.9, 198.51.100.21"), settings)

    assert original == spoofed
    assert other_client != original


def test_untrusted_direct_peer_cannot_choose_its_quota_identity() -> None:
    settings = Settings(
        environment="test",
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="10.0.0.0/8",
    )

    first = client_quota_key(
        Request(
            {
                "type": "http",
                "client": ("198.51.100.40", 1234),
                "headers": [(b"x-forwarded-for", b"203.0.113.1")],
            }
        ),
        settings,
    )
    spoofed = client_quota_key(
        Request(
            {
                "type": "http",
                "client": ("198.51.100.40", 1234),
                "headers": [(b"x-forwarded-for", b"203.0.113.99")],
            }
        ),
        settings,
    )

    assert first == spoofed


def test_access_logger_is_disabled_to_keep_signed_queries_out_of_logs() -> None:
    configure_logging()

    assert logging.getLogger("uvicorn.access").disabled is True


def test_production_rejects_direct_peers_outside_trusted_proxy_cidrs(tmp_path: Path) -> None:
    settings = Settings(
        environment="production",
        cors_origins="https://songdance.example",
        database_url=f"sqlite:///{tmp_path / 'production.sqlite3'}",
        storage_backend="local",
        local_storage_path=tmp_path / "storage",
        temp_path=tmp_path / "tmp",
        quota_backend="redis",
        trusted_proxy_hops=1,
        trusted_proxy_cidrs="10.0.0.0/8",
        download_signing_secret="a-unique-production-secret-with-32-characters",
    )
    app = create_app(
        settings=settings,
        storage=LocalObjectStorage(settings.local_storage_path),
        job_queue=RecordingQueue(),
        job_quota=MemoryJobQuota(settings),
    )

    with TestClient(app, client=("198.51.100.40", 1234)) as direct:
        rejected = direct.get("/health")
    with TestClient(app, client=("10.0.0.8", 1234)) as trusted:
        accepted = trusted.get("/health")

    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "UNTRUSTED_PROXY"
    assert accepted.status_code == 200
    app.state.engine.dispose()


def test_active_limit_returns_429_without_creating_a_second_job(strict_client) -> None:
    first = create_job(strict_client)
    blocked = create_job(strict_client)

    assert first.status_code == 201
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "30"
    assert blocked.json()["detail"]["code"] == "ACTIVE_JOB_LIMIT"
    with strict_client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(TranscriptionJob.id))) == 1

    assert strict_client.delete(f"/jobs/{first.json()['id']}").status_code == 204
    assert create_job(strict_client).status_code == 201


def test_hourly_limit_counts_completed_jobs_and_preserves_retry_time(tmp_path: Path) -> None:
    app = make_test_app(
        tmp_path,
        hourly_job_limit=3,
        client_active_job_limit=2,
        global_active_job_limit=10,
    )
    with TestClient(app) as client:
        for _ in range(3):
            response = create_job(client)
            assert response.status_code == 201
            client.app.state.job_quota.complete(response.json()["id"])
        blocked = create_job(client)
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "HOURLY_LIMIT"
        assert 1 <= int(blocked.headers["retry-after"]) <= 3600
        with client.app.state.session_factory() as session:
            assert session.scalar(select(func.count(TranscriptionJob.id))) == 3
    app.state.engine.dispose()


def test_global_and_daily_fuses_are_independent(tmp_path: Path) -> None:
    settings = Settings(
        environment="test",
        hourly_job_limit=10,
        client_active_job_limit=2,
        global_active_job_limit=2,
        daily_job_limit=2,
    )
    quota = MemoryJobQuota(settings)
    quota.reserve("job-a", "client-a")
    quota.reserve("job-b", "client-b")
    with pytest.raises(QuotaExceeded) as global_error:
        quota.reserve("job-c", "client-c")
    assert global_error.value.code == "GLOBAL_CAPACITY"
    assert global_error.value.retry_after == 60

    quota.complete("job-a")
    quota.complete("job-b")
    with pytest.raises(QuotaExceeded) as daily_error:
        quota.reserve("job-c", "client-c")
    assert daily_error.value.code == "DAILY_CAPACITY"


def test_memory_event_quota_is_atomic_across_concurrent_requests() -> None:
    settings = Settings(
        environment="test",
        analytics_job_event_limit_per_minute=10,
        analytics_client_event_limit_per_minute=20,
        analytics_global_event_limit_per_minute=20,
    )
    quota = MemoryJobQuota(settings)

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


def test_invalid_upload_cancels_its_reservation(strict_client) -> None:
    invalid = create_job(
        strict_client,
        files={"audio_file": ("bad.wav", b"not audio", "audio/wav")},
    )
    traversal = create_job(
        strict_client,
        files={"audio_file": ("../piano.wav", wav_bytes(), "audio/wav")},
    )

    assert invalid.status_code == traversal.status_code == 422
    assert create_job(strict_client).status_code == 201


def test_source_storage_write_has_a_committed_database_intent(tmp_path: Path) -> None:
    app = make_test_app(tmp_path)
    asserting_storage = IntentAssertingStorage(
        app.state.storage,
        app.state.session_factory,
    )
    app.state.storage = asserting_storage
    with TestClient(app) as client:
        created = create_job(client)
        assert created.status_code == 201
        assert asserting_storage.intent_seen is True
        assert client.delete(f"/jobs/{created.json()['id']}").status_code == 204
    app.state.engine.dispose()


def test_fast_worker_progress_is_not_overwritten_after_enqueue(tmp_path: Path) -> None:
    app = make_test_app(tmp_path)
    app.state.job_queue = AdvancingQueue(app.state.session_factory)
    with TestClient(app) as client:
        created = create_job(client)

        assert created.status_code == 201
        assert created.json()["status"] == "running"
        assert created.json()["stage"] == "preprocessing"
        assert client.delete(f"/jobs/{created.json()['id']}").status_code == 204
    app.state.engine.dispose()


def test_cleanup_deletes_objects_and_metadata_but_retries_storage_failure(api_client) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    pipeline_dir = client.app.state.settings.temp_path / f"pipeline-{job_id[:8]}-hardcrash"
    pipeline_dir.mkdir(parents=True)
    (pipeline_dir / "source.wav").write_bytes(b"private audio")
    with client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    original_storage = client.app.state.storage
    client.app.state.storage = AlwaysFailDeleteStorage(original_storage)
    failed = cleanup_expired_jobs(
        client.app.state.session_factory,
        client.app.state.storage,
        client.app.state.settings,
    )
    assert failed.deleted == 0 and failed.failed == 1
    with client.app.state.session_factory() as session:
        failed_job = session.get(TranscriptionJob, job_id)
        assert failed_job is not None
        assert failed_job.error_code == "DELETE_FAILED"
    assert (storage_path / f"jobs/{job_id}/source.wav").is_file()
    assert pipeline_dir.is_dir()

    completed = cleanup_expired_jobs(
        client.app.state.session_factory,
        original_storage,
        client.app.state.settings,
    )
    assert completed.deleted == 1 and completed.failed == 0
    with client.app.state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None
    assert not (storage_path / f"jobs/{job_id}/source.wav").exists()
    assert not pipeline_dir.exists()


def test_stale_temp_cleanup_is_age_limited_and_does_not_follow_symlinks(tmp_path: Path) -> None:
    settings = Settings(environment="test", temp_path=tmp_path / "tmp", temp_file_ttl_seconds=60)
    settings.temp_path.mkdir(parents=True)
    old_pipeline = settings.temp_path / "pipeline-abcdefgh-crash"
    recent_pipeline = settings.temp_path / "pipeline-abcdefgh-active"
    old_pipeline.mkdir()
    recent_pipeline.mkdir()
    (old_pipeline / "source.wav").write_bytes(b"old private audio")
    (recent_pipeline / "source.wav").write_bytes(b"active private audio")
    downloads = settings.temp_path / "downloads"
    downloads.mkdir()
    old_download = downloads / f"{'a' * 32}.wav"
    old_download.write_bytes(b"old download")
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"must survive")
    safe_link = settings.temp_path / "pipeline-abcdefgh-symlink"
    safe_link.symlink_to(outside)
    old_time = datetime.now(UTC).timestamp() - 61
    for entry in (old_pipeline, old_download, safe_link):
        os.utime(entry, (old_time, old_time), follow_symlinks=False)

    result = cleanup_stale_temp_files(settings)

    assert result.deleted == 3 and result.failed == 0
    assert not old_pipeline.exists() and not old_download.exists() and not safe_link.exists()
    assert recent_pipeline.is_dir()
    assert outside.read_bytes() == b"must survive"


def test_stale_upload_intent_is_removed_and_releases_active_quota(strict_client) -> None:
    first = create_job(strict_client)
    job_id = first.json()["id"]
    now = datetime.now(UTC)
    with strict_client.app.state.session_factory() as session:
        job = session.get(TranscriptionJob, job_id)
        assert job is not None
        job.stage = "upload"
        job.updated_at = now - timedelta(
            seconds=strict_client.app.state.settings.upload_intent_timeout_seconds + 1
        )
        session.commit()

    blocked = create_job(strict_client)
    assert blocked.status_code == 429
    cleaned = cleanup_expired_jobs(
        strict_client.app.state.session_factory,
        strict_client.app.state.storage,
        strict_client.app.state.settings,
        now=now,
        job_quota=strict_client.app.state.job_quota,
    )

    assert cleaned.deleted == 1 and cleaned.failed == 0
    assert strict_client.get(f"/jobs/{job_id}").status_code == 404
    assert create_job(strict_client).status_code == 201


def test_delete_racing_an_artifact_upload_leaves_no_orphan(api_client, monkeypatch) -> None:
    client, _queue, storage_path = api_client
    job_id = create_job(client).json()["id"]
    original_storage = client.app.state.storage
    racing_storage = DeleteAfterArtifactStorage(original_storage, client, job_id)
    client.app.state.storage = racing_storage
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)

    run_service(client, job_id)

    assert racing_storage.delete_status == 204
    assert client.get(f"/jobs/{job_id}").status_code == 404
    assert not any(path.is_file() for path in (storage_path / f"jobs/{job_id}").rglob("*"))
    with client.app.state.session_factory() as session:
        assert session.get(TranscriptionJob, job_id) is None


def test_analytics_accepts_whitelist_and_never_stores_raw_job_id(api_client) -> None:
    client, _queue, _storage = api_client
    job_id = create_job(client).json()["id"]

    accepted = client.post(
        "/events",
        json={"event_name": "result_viewed", "job_id": job_id, "properties": {"view": "score"}},
    )
    rejected = client.post(
        "/events",
        json={
            "event_name": "result_viewed",
            "job_id": job_id,
            "properties": {"view": "score", "url": "https://private.example/audio"},
        },
    )

    assert accepted.status_code == 202
    assert rejected.status_code == 422
    with client.app.state.session_factory() as session:
        event = session.scalar(
            select(AnalyticsEvent).where(AnalyticsEvent.event_name == "result_viewed")
        )
        assert event is not None
        assert event.job_id_hash != job_id and len(event.job_id_hash or "") == 64
        assert json.loads(event.properties) == {"view": "score"}
        serialized = event.job_id_hash + event.properties
        assert job_id not in serialized and "private.example" not in serialized


def test_product_events_cover_upload_submit_success_playback_and_all_formats(
    api_client, monkeypatch
) -> None:
    client, _queue, _storage = api_client
    assert client.post("/events/upload-started").status_code == 202
    job_id = create_job(client).json()["id"]
    monkeypatch.setattr("app.services.transcription.transcribe_audio", fake_transcription)
    run_service(client, job_id)
    record_terminal_event(client.app.state.session_factory, client.app.state.settings, job_id)

    for event_name, properties in [
        ("playback_started", {"mode": "midi"}),
        ("format_downloaded", {"format": "midi"}),
        ("format_downloaded", {"format": "musicxml"}),
        ("format_downloaded", {"format": "pdf"}),
    ]:
        response = client.post(
            "/events",
            json={"event_name": event_name, "job_id": job_id, "properties": properties},
        )
        assert response.status_code == 202

    with client.app.state.session_factory() as session:
        all_names = list(session.scalars(select(AnalyticsEvent.event_name)))

    assert {
        "upload_started",
        "transcription_submitted",
        "job_succeeded",
        "playback_started",
        "format_downloaded",
    }.issubset(all_names)


def test_client_event_endpoint_has_a_per_job_rate_boundary(api_client) -> None:
    client, _queue, _storage = api_client
    job_id = create_job(client).json()["id"]

    for _ in range(10):
        assert (
            client.post(
                "/events",
                json={
                    "event_name": "result_viewed",
                    "job_id": job_id,
                    "properties": {"view": "score"},
                },
            ).status_code
            == 202
        )
    blocked = client.post(
        "/events",
        json={"event_name": "result_viewed", "job_id": job_id, "properties": {"view": "score"}},
    )

    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["retry-after"]) <= 60
    assert blocked.json()["detail"]["code"] == "EVENT_JOB_LIMIT"


def test_request_size_and_request_id_boundaries(tmp_path: Path) -> None:
    app = make_test_app(tmp_path, max_request_bytes=100)
    with TestClient(app) as client:
        oversized = client.post(
            "/events",
            content=b"x" * 101,
            headers={"Content-Type": "application/json", "X-Request-ID": "bad id"},
        )
        assert oversized.status_code == 413
        assert oversized.json()["detail"]["code"] == "REQUEST_TOO_LARGE"
        assert oversized.headers["x-request-id"] != "bad id"

        health = client.get("/health", headers={"X-Request-ID": "safe-request-123"})
        assert health.status_code == 200
        assert health.headers["x-request-id"] == "safe-request-123"
    app.state.engine.dispose()


def test_streamed_request_without_content_length_is_still_limited() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )
    sent: list[dict[str, object]] = []

    async def receive():
        return next(incoming)

    async def send(message):
        sent.append(message)

    async def consume_app(_scope, receive_body, send_response):
        while True:
            message = await receive_body()
            if not message.get("more_body"):
                break
        await send_response({"type": "http.response.start", "status": 200, "headers": []})

    middleware = RequestSizeLimitMiddleware(consume_app, max_bytes=5)
    asyncio.run(
        middleware(
            {"type": "http", "headers": []},
            receive,
            send,
        )
    )

    assert sent[0]["status"] == 413


def test_cors_rejects_unlisted_origins(strict_client) -> None:
    headers = {
        "Origin": "https://attacker.example",
        "Access-Control-Request-Method": "POST",
    }
    rejected = strict_client.options("/jobs", headers=headers)
    accepted = strict_client.options(
        "/jobs", headers={**headers, "Origin": "http://localhost:3000"}
    )

    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers
    assert accepted.status_code == 200
    assert accepted.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_allows_next_development_fallback_port(strict_client) -> None:
    accepted = strict_client.options(
        "/jobs",
        headers={
            "Origin": "http://localhost:3001",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert accepted.status_code == 200
    assert accepted.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_cors_allows_loopback_development_origin(strict_client) -> None:
    accepted = strict_client.options(
        "/jobs",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert accepted.status_code == 200
    assert accepted.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"


def test_cross_site_simple_multipart_post_is_rejected_before_job_creation(strict_client) -> None:
    rejected = create_job(
        strict_client,
        headers={"Origin": "https://attacker.example"},
    )

    assert rejected.status_code == 403
    assert rejected.json()["detail"]["code"] == "ORIGIN_REJECTED"
    assert "access-control-allow-origin" not in rejected.headers
    with strict_client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(TranscriptionJob.id))) == 0

    accepted = create_job(
        strict_client,
        headers={"Origin": "http://localhost:3000"},
    )
    assert accepted.status_code == 201
    assert accepted.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_proxy_origin_enforcement_accepts_public_same_origin(strict_client) -> None:
    accepted = strict_client.post(
        "/events/upload-started",
        headers={
            "Host": "demo.modelscope.example",
            "Origin": "https://demo.modelscope.example",
            "X-Forwarded-Proto": "https",
        },
    )

    assert accepted.status_code == 202


def test_logs_use_route_template_and_pipeline_records_safe_failure(api_client, monkeypatch) -> None:
    client, _queue, _storage = api_client
    job_id = create_job(client).json()["id"]
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    try:
        client.get(f"/jobs/{job_id}", headers={"X-Request-ID": "phase6-log-test"})
    finally:
        logger.removeHandler(handler)
    captured = stream.getvalue()
    assert "/jobs/{job_id}" in captured
    assert job_id not in captured
    assert "source.wav" not in captured

    monkeypatch.setattr(
        "app.services.transcription.transcribe_audio",
            lambda _path, **_kwargs: (_ for _ in ()).throw(ModelInferenceError()),
    )
    run_service(client, job_id)
    with client.app.state.session_factory() as session:
        events = list(
            session.scalars(
                select(AnalyticsEvent).where(AnalyticsEvent.event_name == "pipeline_stage")
            )
        )
    properties = [json.loads(event.properties) for event in events]
    failed = next(item for item in properties if item["stage"] == "transcribing")
    assert failed["status"] == "failed"
    assert failed["error_code"] == "MODEL_INFERENCE_FAILED"
    assert failed["model_version"].startswith("basic-pitch-")
    assert failed["duration_ms"] >= 0


class AlwaysFailDeleteStorage:
    def __init__(self, delegate) -> None:
        self.delegate = delegate

    def delete(self, key: str) -> None:
        raise ConnectionError("storage unavailable")

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


class DeleteAfterArtifactStorage:
    def __init__(self, delegate, client: TestClient, job_id: str) -> None:
        self.delegate = delegate
        self.client = client
        self.job_id = job_id
        self.delete_status: int | None = None

    def put_file(self, key: str, source: Path, content_type: str) -> None:
        self.delegate.put_file(key, source, content_type)
        if "/artifacts/" in key and self.delete_status is None:
            self.delete_status = self.client.delete(f"/jobs/{self.job_id}").status_code

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


class IntentAssertingStorage:
    def __init__(self, delegate, factory) -> None:
        self.delegate = delegate
        self.factory = factory
        self.intent_seen = False

    def put_file(self, key: str, source: Path, content_type: str) -> None:
        if key.endswith("/source.wav"):
            job_id = key.split("/")[1]
            with self.factory() as session:
                job = session.get(TranscriptionJob, job_id)
                assert job is not None
                assert job.stage == "upload"
                assert job.source_asset.storage_key == key
                self.intent_seen = True
        self.delegate.put_file(key, source, content_type)

    def __getattr__(self, name: str):
        return getattr(self.delegate, name)


class AdvancingQueue:
    def __init__(self, factory) -> None:
        self.factory = factory

    def enqueue(self, job_id: str, _attempt: int) -> str:
        with self.factory() as session:
            job = session.get(TranscriptionJob, job_id)
            assert job is not None
            job.status = "running"
            job.stage = "preprocessing"
            session.commit()
        return f"advanced:{job_id}"
