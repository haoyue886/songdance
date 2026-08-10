import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app.pipeline.errors import PipelineError

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def parse_youtube_video_id(value: str) -> str:
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise PipelineError("YOUTUBE_URL_INVALID", "YouTube 链接格式无效") from error
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as error:
        raise PipelineError("YOUTUBE_URL_INVALID", "YouTube 链接格式无效") from error
    if (
        parsed.scheme != "https"
        or host not in YOUTUBE_HOSTS
        or parsed.username
        or parsed.password
        or port not in {None, 443}
        or parsed.fragment
    ):
        raise PipelineError("YOUTUBE_URL_INVALID", "只接受 youtube.com 或 youtu.be 的 HTTPS 链接")

    if host == "youtu.be":
        path = parsed.path.strip("/")
        video_id = path if "/" not in path else ""
    elif parsed.path == "/watch":
        values = parse_qs(parsed.query).get("v", [])
        video_id = values[0] if len(values) == 1 else ""
    elif parsed.path.startswith(("/shorts/", "/embed/")):
        parts = parsed.path.strip("/").split("/")
        video_id = parts[1] if len(parts) == 2 else ""
    else:
        video_id = ""
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise PipelineError("YOUTUBE_URL_INVALID", "YouTube 链接缺少有效的视频 ID")
    return video_id


def download_youtube_clip(
    video_id: str,
    start_sec: float,
    end_sec: float,
    destination: Path,
    timeout_seconds: int,
) -> None:
    canonical_url = f"https://www.youtube.com/watch?v={video_id}"
    template = destination.with_suffix(".%(ext)s")
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--ignore-config",
        "--xff",
        "never",
        "--proxy",
        "",
        "--js-runtimes",
        "node",
        "--no-cookies",
        "--no-cookies-from-browser",
        "--no-cache-dir",
        "--no-playlist",
        "--no-wait-for-video",
        "--match-filters",
        "live_status = not_live",
        "--format",
        "bestaudio[acodec!=none]",
        "--quiet",
        "--no-warnings",
        "--no-progress",
        "--socket-timeout",
        "15",
        "--retries",
        "1",
        "--extractor-retries",
        "1",
        "--fragment-retries",
        "1",
        "--download-sections",
        f"*{start_sec:.3f}-{end_sec:.3f}",
        "--force-keyframes-at-cuts",
        "--extract-audio",
        "--audio-format",
        "wav",
        "--postprocessor-args",
        "ExtractAudio+ffmpeg_o:-ac 1 -ar 44100",
        "--output",
        str(template),
        canonical_url,
    ]
    try:
        result = _run_command(command, timeout_seconds)
    except subprocess.TimeoutExpired as error:
        raise PipelineError("YOUTUBE_TIMEOUT", "YouTube 获取超时，请改用本地上传") from error
    if result.returncode != 0:
        raise _download_error(result.stderr)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise PipelineError("YOUTUBE_UNAVAILABLE", "YouTube 音频不可用，请改用本地上传")


def _run_command(
    command: list[str], timeout_seconds: int | float
) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        process.communicate()
        return
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()


def _download_error(stderr: str) -> PipelineError:
    message = stderr.lower()
    if any(token in message for token in ("private video", "sign in", "login", "members-only")):
        return PipelineError("YOUTUBE_RESTRICTED", "该视频需要登录或不是公开内容，请改用本地上传")
    if any(token in message for token in ("not available in your country", "geo restricted")):
        return PipelineError("YOUTUBE_REGION_RESTRICTED", "该视频受地区限制，请改用本地上传")
    if (
        "live event" in message
        or "is live" in message
        or ("does not pass filter" in message and "live_status" in message)
    ):
        return PipelineError("YOUTUBE_LIVE_UNSUPPORTED", "暂不支持直播内容，请改用本地上传")
    return PipelineError("YOUTUBE_UNAVAILABLE", "YouTube 音频不可用，请改用本地上传")
