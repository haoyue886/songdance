import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_AUDIO_BYTES = 25 * 1024 * 1024
MIN_CLIP_SECONDS = 1
MAX_CLIP_SECONDS = 90

MIME_TYPES = {
    "mp3": {"audio/mpeg", "audio/mp3"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
    "m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac"},
}
CANONICAL_MIME = {"mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4"}


class AudioValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedAudio:
    format: str
    mime_type: str
    duration: float


def _sniff_format(path: Path) -> str | None:
    with path.open("rb") as file:
        header = file.read(16)
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    is_mp3_frame = len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
    if len(header) >= 3 and (header[:3] == b"ID3" or is_mp3_frame):
        return "mp3"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "m4a"
    return None


def _probe(path: Path) -> tuple[float, list[str]]:
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        payload = json.loads(completed.stdout)
        duration = float(payload.get("format", {}).get("duration", 0))
        stream_types = [str(stream.get("codec_type")) for stream in payload.get("streams", [])]
    except (subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
        raise AudioValidationError("AUDIO_DECODE_FAILED", "服务器无法解码这个音频文件") from error
    return duration, stream_types


def validate_audio_file(path: Path, filename: str, declared_mime: str | None) -> ValidatedAudio:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in MIME_TYPES:
        raise AudioValidationError("UNSUPPORTED_FORMAT", "只支持 MP3、WAV 或 M4A 文件")
    detected = _sniff_format(path)
    if detected is None:
        raise AudioValidationError("INVALID_SIGNATURE", "文件内容不是可识别的音频")
    if detected != extension:
        raise AudioValidationError("FORMAT_MISMATCH", "文件扩展名与实际内容不一致")
    normalized_mime = (declared_mime or "").lower().split(";", 1)[0].strip()
    if normalized_mime and normalized_mime != "application/octet-stream":
        if normalized_mime not in MIME_TYPES[detected]:
            raise AudioValidationError("MIME_MISMATCH", "文件 MIME 类型与实际内容不一致")

    duration, stream_types = _probe(path)
    if "video" in stream_types:
        raise AudioValidationError("VIDEO_NOT_ALLOWED", "文件包含视频轨，请上传纯音频")
    if "audio" not in stream_types or duration < MIN_CLIP_SECONDS:
        raise AudioValidationError("AUDIO_TOO_SHORT", "音频必须至少 1 秒")
    return ValidatedAudio(detected, CANONICAL_MIME[detected], duration)


def validate_clip(start_sec: float, end_sec: float, duration: float) -> None:
    if start_sec < 0 or end_sec > duration + 0.01 or end_sec <= start_sec:
        raise AudioValidationError("INVALID_CLIP", "转录区间超出音频范围")
    clip_length = end_sec - start_sec
    if clip_length < MIN_CLIP_SECONDS or clip_length > MAX_CLIP_SECONDS:
        raise AudioValidationError("INVALID_CLIP", "转录片段必须在 1 到 90 秒之间")


def extract_clip_to_wav(
    source: Path, destination: Path, start_sec: float, end_sec: float
) -> ValidatedAudio:
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                str(start_sec),
                "-i",
                str(source),
                "-t",
                str(end_sec - start_sec),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.SubprocessError as error:
        raise AudioValidationError(
            "CLIP_EXTRACTION_FAILED", "服务器无法提取所选音频片段"
        ) from error

    result = validate_audio_file(destination, destination.name, "audio/wav")
    if abs(result.duration - (end_sec - start_sec)) > 0.25:
        raise AudioValidationError("CLIP_EXTRACTION_FAILED", "提取后的音频长度不正确")
    return result
