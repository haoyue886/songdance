import asyncio
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import httpx
import pytest
from sqlalchemy import func, select

from app.models import TranscriptionJob
from app.services.audio_validation import AudioValidationError
from app.services.media_process import MAX_CAPTURE_BYTES, run_media
from app.services.quota import MemoryJobQuota, QuotaExceeded
from app.settings import Settings
from tests.conftest import wav_bytes
from tests.test_jobs import create_job


@pytest.mark.parametrize("paid", [False, True])
def test_canceled_admissions_preserve_safety_counts_and_release_active_slots(paid):
    quota = MemoryJobQuota(
        Settings(
            _env_file=None,
            hourly_job_limit=1,
            paid_ip_hourly_job_limit=1,
            client_active_job_limit=1,
            global_active_job_limit=1,
            daily_job_limit=2,
        )
    )
    quota.reserve("first", "client", paid=paid)
    quota.cancel("first")
    quota.cancel("first")
    with pytest.raises(QuotaExceeded) as error:
        quota.reserve("repeat", "client", paid=paid)
    assert error.value.code == ("IP_SECURITY_LIMIT" if paid else "HOURLY_LIMIT")
    quota.reserve("second", "other-client", paid=paid)
    quota.cancel("second")
    with pytest.raises(QuotaExceeded) as error:
        quota.reserve("third", "third-client", paid=paid)
    assert error.value.code == "DAILY_CAPACITY"


@pytest.mark.parametrize("durable", [False, True])
def test_failed_decodes_are_throttled_before_reentering_parser(api_client, monkeypatch, durable):
    client, queue, storage = api_client
    settings = client.app.state.settings
    settings.reliable_queue_enabled = durable
    settings.hourly_job_limit = 2
    calls = []

    def fail(*_):
        calls.append(1)
        raise AudioValidationError("AUDIO_DECODE_FAILED", "Invalid audio")

    module = "app.services.durable_jobs" if durable else "app.routes.jobs"
    monkeypatch.setattr(module + ".validate_audio_file", fail)
    assert create_job(client).status_code == 422
    assert create_job(client).status_code == 422
    blocked = create_job(client)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["code"] == "HOURLY_LIMIT"
    assert int(blocked.headers["retry-after"]) > 0
    assert calls == [1, 1] and queue.calls == []
    assert not any(storage.rglob("*"))
    assert not any(settings.temp_path.iterdir())
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(TranscriptionJob.id))) == 0


@pytest.mark.parametrize("durable", [False, True])
@pytest.mark.parametrize("phase", ["validate_audio_file", "extract_clip_to_wav"])
def test_health_responds_while_upload_media_work_is_running(
    api_client,
    monkeypatch,
    durable,
    phase,
):
    from app.routes import jobs
    from app.services import durable_jobs

    client, _, _ = api_client
    client.app.state.settings.reliable_queue_enabled = durable
    module = durable_jobs if durable else jobs
    original = getattr(module, phase)
    started, finish = Event(), Event()

    def slow(*args):
        started.set()
        assert finish.wait(5), "Test did not release parser"
        return original(*args)

    monkeypatch.setattr(module, phase, slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        upload = pool.submit(create_job, client)
        try:
            assert started.wait(3)
            health = pool.submit(client.get, "/health")
            assert health.result(timeout=1).status_code == 200
        finally:
            finish.set()
        assert upload.result(timeout=5).status_code == 201


def fake_probe(tmp_path: Path, monkeypatch, body: str) -> Path:
    tool = tmp_path / "ffprobe"
    tool.write_text(f"#!{sys.executable}\n" + body)
    tool.chmod(0o700)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.defpath)
    return tool


@pytest.mark.parametrize("durable", [False, True])
def test_cancelled_request_does_not_remove_files_or_capacity_under_running_media(
    api_client,
    monkeypatch,
    durable,
):
    from app.routes import jobs
    from app.services import durable_jobs

    client, _, _ = api_client
    settings = client.app.state.settings
    settings.reliable_queue_enabled = durable
    module = durable_jobs if durable else jobs
    started, finish = Event(), Event()
    paths = []

    def slow_extract(source, destination, *_):
        paths.extend([source, destination])
        started.set()
        assert finish.wait(5)
        assert source.is_file(), "Request removed an input still used by media"
        destination.write_bytes(b"late media output")
        raise AudioValidationError("CLIP_EXTRACTION_FAILED", "Canceled work")

    monkeypatch.setattr(module, "extract_clip_to_wav", slow_extract)

    async def scenario():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app),
            base_url="http://testserver",
        ) as http:
            upload = asyncio.create_task(
                http.post(
                    "/jobs",
                    files={"audio_file": ("audio.wav", wav_bytes(), "audio/wav")},
                    data={"start_sec": 0, "end_sec": 1.5, "rights_confirmed": "true"},
                )
            )
            try:
                assert await asyncio.to_thread(started.wait, 3)
                upload.cancel()
                await asyncio.sleep(0.05)
                assert not upload.done(), "Canceled HTTP must first join its media work"
                assert paths[0].is_file()
                assert client.app.state.job_quota._jobs
            finally:
                finish.set()
                with pytest.raises(asyncio.CancelledError):
                    await upload
            assert not client.app.state.job_quota._jobs
            assert all(not p.exists() for p in paths)

    asyncio.run(scenario())


def test_child_has_limits_and_does_not_inherit_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SONGDANCE_S3_SECRET_KEY", "must-never-reach-media")
    fake_probe(
        tmp_path,
        monkeypatch,
        """
import resource,json,os
print(json.dumps({'cpu':resource.getrlimit(resource.RLIMIT_CPU),
 'core':resource.getrlimit(resource.RLIMIT_CORE),
 'files':resource.getrlimit(resource.RLIMIT_FSIZE),
 'memory':resource.getrlimit(resource.RLIMIT_AS), 'env':dict(os.environ)}))
""",
    )
    data = json.loads(run_media(["ffprobe"], timeout=3))
    assert data["cpu"] == [10, 10] and data["core"] == [0, 0]
    assert data["files"] == [512 * 1024] * 2
    if sys.platform == "linux":
        assert data["memory"] == [512 * 1024 * 1024] * 2
    assert "SONGDANCE_S3_SECRET_KEY" not in data["env"]


def test_child_output_is_bounded_before_loading_into_parent(tmp_path, monkeypatch):
    fake_probe(tmp_path, monkeypatch, f"print('x' * {MAX_CAPTURE_BYTES + 1})\n")
    with pytest.raises(subprocess.SubprocessError, match="output exceeded"):
        run_media(["ffprobe"], timeout=3)


def test_child_file_limit_is_enforced_by_kernel(tmp_path, monkeypatch):
    destination = tmp_path / "oversized"
    fake_probe(
        tmp_path,
        monkeypatch,
        """
import sys
with open(sys.argv[1], 'wb') as f:
 f.write(b'x' * (1024 * 1024))
""",
    )
    with pytest.raises(subprocess.CalledProcessError):
        run_media(["ffprobe", str(destination)], timeout=3)
    assert destination.stat().st_size <= 512 * 1024


def test_timeout_reaps_media_process_and_kills_its_descendant(tmp_path, monkeypatch):
    pid_file = tmp_path / "child.pid"
    fake_probe(
        tmp_path,
        monkeypatch,
        """
import subprocess,sys,time,os
child=subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
open(sys.argv[1], 'w').write(f'{os.getpid()} {child.pid}')
time.sleep(30)
""",
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_media(["ffprobe", str(pid_file)], timeout=0.5)
    parent, child = map(int, pid_file.read_text().split())
    with pytest.raises(ProcessLookupError):
        os.kill(parent, 0)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        # A killed grandchild can remain a zombie until the host init reaps it.
        stat = Path(f"/proc/{child}/stat")
        if sys.platform == "linux" and (not stat.exists() or stat.read_text().split()[2] == "Z"):
            break
        time.sleep(0.02)
    else:
        pytest.fail("Media descendant remained running after timeout")


@pytest.mark.parametrize(
    "output",
    [
        "[]",
        '{"format":[],"streams":[]}',
        '{"format":{"duration":"NaN"},"streams":[]}',
        '{"format":{"duration":null},"streams":[]}',
        '{"format":{"duration":{}},"streams":[]}',
        '{"format":{},"streams":[0]}',
    ],
)
def test_malformed_probe_metadata_is_a_stable_validation_error(tmp_path, monkeypatch, output):
    from app.services.audio_validation import validate_audio_file

    source = tmp_path / "valid.wav"
    source.write_bytes(wav_bytes())
    monkeypatch.setattr("app.services.audio_validation.run_media", lambda *_a, **_kw: output)
    with pytest.raises(AudioValidationError) as error:
        validate_audio_file(source, source.name, "audio/wav")
    assert error.value.code == "AUDIO_DECODE_FAILED"
