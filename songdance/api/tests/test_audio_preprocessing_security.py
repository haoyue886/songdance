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


@pytest.mark.parametrize("failure", ["old_abi", "restrict_self", "seccomp"])
def test_linux_isolation_failure_never_executes_media(tmp_path, monkeypatch, failure):
    from unittest.mock import Mock

    from app.services import _media_limits as limits

    executable = tmp_path / "ffprobe"
    executable.touch()
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(limits.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(sys, "argv", ["helper", "ffprobe", "[]", "[]"])
    monkeypatch.setattr(limits.shutil, "which", lambda _tool: str(executable))
    monkeypatch.setattr(limits.resource, "setrlimit", Mock())
    monkeypatch.setattr(limits.resource, "getrlimit", lambda _kind: (-1, -1))
    libc = Mock()
    libc.prctl.return_value = 0
    monkeypatch.setattr(limits.ctypes, "CDLL", lambda *_a, **_kw: libc)

    def fake_syscall(_libc, number, *arguments):
        if number == 444:
            return (3 if failure == "old_abi" else 4) if arguments[-1] == 1 else 42
        if number == 446 and failure == "restrict_self":
            raise PermissionError("synthetic restrict_self failure")
        return 0

    monkeypatch.setattr(limits, "_syscall", fake_syscall)
    monkeypatch.setattr(limits, "_add_path_rule", Mock())
    monkeypatch.setattr(limits, "_allow_path", Mock())
    monkeypatch.setattr(limits.os, "close", Mock())
    if failure == "seccomp":
        monkeypatch.setattr(
            limits,
            "_install_no_socket_filter",
            Mock(side_effect=PermissionError("synthetic seccomp failure")),
        )
    execute = Mock()
    monkeypatch.setattr(limits.os, "execv", execute)
    with pytest.raises(OSError):
        limits.main()
    execute.assert_not_called()


@pytest.mark.parametrize(
    ("machine", "architecture", "blocked"),
    [
        ("aarch64", 0xC00000B7, (5, 52, 88, 198, 199, 29, 117)),
        ("x86_64", 0xC000003E, (90, 92, 188, 280, 41, 53, 16, 101)),
    ],
)
def test_seccomp_program_rejects_network_metadata_and_abi_bypasses(
    monkeypatch, machine, architecture, blocked
):
    import ctypes

    from app.services import _media_limits as limits

    instructions = []

    class Libc:
        def prctl(self, option, mode, address):
            assert option == limits.PR_SET_SECCOMP and mode == limits.SECCOMP_MODE_FILTER
            program = ctypes.cast(address, ctypes.POINTER(limits.SockFprog)).contents
            instructions.extend(
                (row.code, row.jt, row.jf, row.k) for row in program.filter[: program.length]
            )
            return 0

    monkeypatch.setattr(limits.platform, "machine", lambda: machine)
    limits._install_no_socket_filter(Libc())

    def evaluate(number, arch=architecture, ioctl_request=0):
        index, value = 0, 0
        while index < len(instructions):
            code, yes, no, operand = instructions[index]
            if code == limits.BPF_LD_W_ABS:
                value = {0: number, 4: arch, 24: ioctl_request}[operand]
            elif code == limits.BPF_JMP_JEQ_K:
                index += yes if value == operand else no
            elif code == limits.BPF_JMP_JSET_K:
                index += yes if value & operand else no
            elif code == limits.BPF_RET_K:
                return operand
            else:
                pytest.fail("Unexpected seccomp instruction")
            index += 1
        pytest.fail("Seccomp program did not return")

    for number in (*blocked, 425, 426, 427, 438, 452, 463, 466, 469):
        assert evaluate(number) == limits.SECCOMP_RET_ERRNO | 1
    assert evaluate(63 if machine == "aarch64" else 0) == limits.SECCOMP_RET_ALLOW
    ioctl = 29 if machine == "aarch64" else 16
    assert evaluate(ioctl, ioctl_request=0x5451) == limits.SECCOMP_RET_ALLOW
    assert evaluate(ioctl, ioctl_request=0x5450) == limits.SECCOMP_RET_ALLOW
    assert evaluate(ioctl, ioctl_request=0x40086602) == limits.SECCOMP_RET_ERRNO | 1
    assert evaluate(0, arch=0x40000003) == limits.SECCOMP_RET_KILL_PROCESS
    if machine == "x86_64":
        assert evaluate(0x40000000 | 41) == limits.SECCOMP_RET_KILL_PROCESS


def test_output_allowlist_never_overwrites_existing_file_or_symlink(tmp_path):
    destination = tmp_path / "clip.wav"
    destination.write_bytes(b"existing output")
    with pytest.raises(FileExistsError):
        run_media(["ffmpeg"], timeout=1, writable_paths=(destination,))
    assert destination.read_bytes() == b"existing output"
    link = tmp_path / "link.wav"
    link.symlink_to(destination)
    with pytest.raises(FileExistsError):
        run_media(["ffmpeg"], timeout=1, writable_paths=(link,))
    assert destination.read_bytes() == b"existing output"


@pytest.mark.skipif(sys.platform != "linux", reason="Landlock is Linux-only")
def test_landlock_limits_media_files_and_blocks_network_sockets(tmp_path, monkeypatch):
    readable = tmp_path / "input.wav"
    readable.write_bytes(wav_bytes())
    writable = tmp_path / "output.wav"
    blocked = tmp_path / "other-job.wav"
    blocked.write_bytes(b"protected sibling")
    protected_stat = blocked.stat()
    fake_probe(
        tmp_path,
        monkeypatch,
        """
import ctypes,errno,json,os,socket,sys
read_ok = open(sys.argv[1], 'rb').read(4) == b'RIFF'
open(sys.argv[2], 'wb').write(b'allowed')
try:
 open(sys.argv[3], 'rb')
 secret_read_blocked = False
except PermissionError:
 secret_read_blocked = True
try:
 open(sys.argv[4], 'wb').write(b'blocked')
 sibling_write_blocked = False
except PermissionError:
 sibling_write_blocked = True
try:
 socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
 sockets_blocked = False
except PermissionError:
 sockets_blocked = True
metadata_blocked = True
for operation in (lambda:os.chmod(sys.argv[4],0), lambda:os.utime(sys.argv[4],(0,0)),
                  lambda:os.setxattr(sys.argv[4],'user.test',b'blocked')):
 try: operation(); metadata_blocked = False
 except PermissionError: pass
libc=ctypes.CDLL(None,use_errno=True)
new_metadata_api_blocked = libc.syscall(469,0,0,0,0) == -1 and ctypes.get_errno() == errno.EPERM
print(json.dumps({'read_ok':read_ok,'secret_read_blocked':secret_read_blocked,
 'sibling_write_blocked':sibling_write_blocked,'sockets_blocked':sockets_blocked,
 'metadata_blocked':metadata_blocked,'new_metadata_api_blocked':new_metadata_api_blocked}))
""",
    )
    result = json.loads(
        run_media(
            ["ffprobe", str(readable), str(writable), "/etc/passwd", str(blocked)],
            timeout=3,
            readable_paths=(readable,),
            writable_paths=(writable,),
        )
    )
    assert result == {
        "read_ok": True,
        "secret_read_blocked": True,
        "sibling_write_blocked": True,
        "sockets_blocked": True,
        "metadata_blocked": True,
        "new_metadata_api_blocked": True,
    }
    assert writable.read_bytes() == b"allowed"
    assert blocked.read_bytes() == b"protected sibling"
    assert blocked.stat().st_mode == protected_stat.st_mode
    assert blocked.stat().st_mtime_ns == protected_stat.st_mtime_ns


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
        run_media(["ffprobe", str(destination)], timeout=3, writable_paths=(destination,))
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
        run_media(["ffprobe", str(pid_file)], timeout=0.5, writable_paths=(pid_file,))
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
