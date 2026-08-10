import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import TranscriptionJob
from app.pipeline.errors import PipelineError
from app.pipeline.youtube import _run_command, download_youtube_clip, parse_youtube_video_id
from app.services.audio_validation import MAX_AUDIO_BYTES
from tests.conftest import wav_bytes

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/shorts/{VIDEO_ID}",
        f"https://youtube.com/embed/{VIDEO_ID}",
    ],
)
def test_youtube_url_parser_accepts_only_supported_https_forms(url: str) -> None:
    assert parse_youtube_video_id(url) == VIDEO_ID


@pytest.mark.parametrize(
    "url",
    [
        f"http://youtu.be/{VIDEO_ID}",
        f"https://youtube.example/watch?v={VIDEO_ID}",
        f"https://youtube.com.evil.example/watch?v={VIDEO_ID}",
        f"https://user:secret@youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com:invalid/watch?v={VIDEO_ID}",
        "https://youtube.com/watch?v=too-short",
        f"https://youtube.com/playlist?list={VIDEO_ID}",
    ],
)
def test_youtube_url_parser_rejects_unsafe_or_unsupported_forms(url: str) -> None:
    with pytest.raises(PipelineError) as error:
        parse_youtube_video_id(url)
    assert error.value.code == "YOUTUBE_URL_INVALID"


def test_youtube_downloader_uses_bounded_anonymous_clip_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "source.wav"
    captured: list[str] = []

    def run(command, timeout_seconds):
        captured.extend(command)
        destination.write_bytes(b"RIFF-test")
        assert timeout_seconds == 120
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.pipeline.youtube._run_command", run)
    download_youtube_clip(VIDEO_ID, 12.5, 42.5, destination, 120)

    assert "--ignore-config" in captured
    assert captured[captured.index("--xff") + 1] == "never"
    assert captured[captured.index("--proxy") + 1] == ""
    assert captured[captured.index("--js-runtimes") + 1] == "node"
    assert "--no-cookies" in captured
    assert "--no-cookies-from-browser" in captured
    assert "--no-cache-dir" in captured
    assert "--cookies" not in captured
    assert "--cookies-from-browser" not in captured
    assert "--no-playlist" in captured
    assert captured[captured.index("--match-filters") + 1] == "live_status = not_live"
    assert captured[captured.index("--format") + 1] == "bestaudio[acodec!=none]"
    assert captured[captured.index("--download-sections") + 1] == "*12.500-42.500"
    assert captured[captured.index("--extractor-retries") + 1] == "1"
    assert captured[captured.index("--postprocessor-args") + 1] == (
        "ExtractAudio+ffmpeg_o:-ac 1 -ar 44100"
    )
    assert captured[-1] == f"https://www.youtube.com/watch?v={VIDEO_ID}"


def test_youtube_downloader_maps_live_filter_rejection_to_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stderr = "Video does not pass filter (live_status = not_live), skipping"
    monkeypatch.setattr(
        "app.pipeline.youtube._run_command",
        lambda command, _timeout: subprocess.CompletedProcess(command, 1, "", stderr),
    )

    with pytest.raises(PipelineError) as error:
        download_youtube_clip(VIDEO_ID, 0, 2, tmp_path / "source.wav", 120)

    assert error.value.code == "YOUTUBE_LIVE_UNSUPPORTED"


def test_youtube_timeout_kills_the_parent_and_spawned_child_process_group(tmp_path: Path) -> None:
    pid_file = tmp_path / "processes.pid"
    script = (
        "import os, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "open(sys.argv[1], 'w').write(f'{os.getpid()} {child.pid}'); "
        "time.sleep(60)"
    )

    with pytest.raises(subprocess.TimeoutExpired):
        _run_command([sys.executable, "-c", script, str(pid_file)], 0.5)

    parent_pid, child_pid = (int(value) for value in pid_file.read_text().split())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and any(
        _process_exists(pid) for pid in (parent_pid, child_pid)
    ):
        time.sleep(0.05)
    assert not _process_exists(parent_pid)
    assert not _process_exists(child_pid)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_youtube_route_is_off_by_default(api_client) -> None:
    client, queue, storage_path = api_client

    response = client.post(
        "/youtube/jobs",
        json={
            "url": f"https://youtu.be/{VIDEO_ID}",
            "start_sec": 0,
            "end_sec": 2,
            "rights_confirmed": True,
        },
    )

    assert client.get("/youtube/config").json() == {"enabled": False}
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "YOUTUBE_DISABLED"
    assert queue.calls == []
    assert not any(storage_path.rglob("*"))


def test_youtube_route_creates_a_standard_job_without_retaining_url(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, queue, storage_path = api_client
    client.app.state.settings.youtube_enabled = True

    def download(_video_id, _start, _end, destination, _timeout):
        destination.write_bytes(wav_bytes(duration=2))

    monkeypatch.setattr("app.routes.youtube.download_youtube_clip", download)
    url = f"https://www.youtube.com/watch?v={VIDEO_ID}&utm_source=private-value"
    response = client.post(
        "/youtube/jobs",
        json={
            "url": url,
            "start_sec": 10,
            "end_sec": 12,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["source_type"] == "youtube"
    assert payload["stage"] == "queued"
    assert len(queue.calls) == 1
    source = storage_path / "jobs" / payload["id"] / "source.wav"
    assert source.is_file()
    assert url.encode() not in (storage_path.parent / "jobs.sqlite3").read_bytes()
    assert not list((storage_path.parent / "tmp").glob("youtube-*"))


def test_youtube_route_releases_capacity_and_falls_back_on_platform_refusal(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, queue, storage_path = api_client
    client.app.state.settings.youtube_enabled = True

    def refuse(*_args):
        raise PipelineError("YOUTUBE_RESTRICTED", "该视频需要登录，请改用本地上传")

    monkeypatch.setattr("app.routes.youtube.download_youtube_clip", refuse)
    response = client.post(
        "/youtube/jobs",
        json={
            "url": f"https://youtu.be/{VIDEO_ID}",
            "start_sec": 0,
            "end_sec": 2,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "YOUTUBE_RESTRICTED"
    assert queue.calls == []
    assert not any(storage_path.rglob("*"))
    assert not list((storage_path.parent / "tmp").glob("youtube-*"))


def test_youtube_route_rejects_over_90_seconds_before_downloading(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, queue, _storage_path = api_client
    client.app.state.settings.youtube_enabled = True
    monkeypatch.setattr(
        "app.routes.youtube.download_youtube_clip",
        lambda *_args: pytest.fail("downloader must not run for an invalid clip"),
    )

    response = client.post(
        "/youtube/jobs",
        json={
            "url": f"https://youtu.be/{VIDEO_ID}",
            "start_sec": 0,
            "end_sec": 90.1,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_CLIP"
    assert queue.calls == []


def test_youtube_route_rolls_back_durable_intent_when_queue_fails(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, queue, storage_path = api_client
    client.app.state.settings.youtube_enabled = True
    queue.error = RuntimeError("redis unavailable")

    def download(_video_id, _start, _end, destination, _timeout):
        destination.write_bytes(wav_bytes(duration=2))

    monkeypatch.setattr("app.routes.youtube.download_youtube_clip", download)
    response = client.post(
        "/youtube/jobs",
        json={
            "url": f"https://youtu.be/{VIDEO_ID}",
            "start_sec": 0,
            "end_sec": 2,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 503
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(TranscriptionJob)) == 0
    assert not list(storage_path.rglob("*.wav"))
    assert not list((storage_path.parent / "tmp").glob("youtube-*"))


def test_youtube_route_rejects_oversized_converted_audio_before_storage(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, queue, storage_path = api_client
    client.app.state.settings.youtube_enabled = True

    def download(_video_id, _start, _end, destination, _timeout):
        with destination.open("wb") as output:
            output.write(b"RIFF")
            output.seek(MAX_AUDIO_BYTES)
            output.write(b"\0")

    monkeypatch.setattr("app.routes.youtube.download_youtube_clip", download)
    response = client.post(
        "/youtube/jobs",
        json={
            "url": f"https://youtu.be/{VIDEO_ID}",
            "start_sec": 0,
            "end_sec": 2,
            "rights_confirmed": True,
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "YOUTUBE_CLIP_TOO_LARGE"
    assert queue.calls == []
    assert not list(storage_path.rglob("*.wav"))
    assert not list((storage_path.parent / "tmp").glob("youtube-*"))
