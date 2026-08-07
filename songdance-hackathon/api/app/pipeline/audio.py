import subprocess
from pathlib import Path

from app.pipeline.errors import AudioPreprocessError, AudioPreprocessTimeoutError


def preprocess_audio(source: Path, destination: Path, timeout_seconds: int = 120) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                "-af",
                "loudnorm=I=-16:LRA=11:TP=-1.5",
                "-c:a",
                "pcm_s16le",
                "-y",
                str(destination),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise AudioPreprocessTimeoutError() from error
    except subprocess.CalledProcessError as error:
        raise AudioPreprocessError("FFmpeg 无法规范化音频") from error
    if not destination.is_file() or destination.stat().st_size <= 44:
        raise AudioPreprocessError("FFmpeg 没有生成有效音频")
