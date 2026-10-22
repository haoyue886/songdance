import subprocess
import tempfile
from pathlib import Path

from app.pipeline.errors import AudioPreprocessError, AudioPreprocessTimeoutError
from app.services.media_process import run_media


def preprocess_audio(source: Path, destination: Path, timeout_seconds: int = 120) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A private output preserves an existing result until normalization succeeds.
        with tempfile.TemporaryDirectory(prefix="normalize-", dir=destination.parent) as raw:
            output = Path(raw) / "normalized.wav"
            run_media(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-protocol_whitelist",
                    "file",
                    "-format_whitelist",
                    "wav",
                    "-f",
                    "wav",
                    "-threads",
                    "1",
                    "-i",
                    str(source),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "22050",
                    "-af",
                    "loudnorm=I=-16:LRA=11:TP=-1.5",
                    "-filter_threads",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    "-threads",
                    "1",
                    "-y",
                    str(output),
                ],
                timeout=timeout_seconds,
                readable_paths=(source,),
                writable_paths=(output,),
            )
            if not output.is_file() or output.stat().st_size <= 44:
                raise AudioPreprocessError("FFmpeg 没有生成有效音频")
            output.replace(destination)
    except subprocess.TimeoutExpired as error:
        raise AudioPreprocessTimeoutError() from error
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        raise AudioPreprocessError("FFmpeg 无法规范化音频") from error
