import hashlib
import json
import subprocess
import tempfile
import urllib.parse
import wave
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/audio"
MANIFEST_PATH = FIXTURE_ROOT / "human-manifest.json"
OUTPUT_DIR = FIXTURE_ROOT / "human-generated"
PROVENANCE_PATH = FIXTURE_ROOT / "human-provenance.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "SongDance regression preparation/0.3 (quality verification)"


def prepare() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    allowed = set(manifest["authorization"]["allowed_licenses"])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    provenance = []
    for case in manifest["cases"]:
        metadata = commons_metadata(case["source_title"])
        license_name = metadata["license"]
        if license_name not in allowed:
            raise RuntimeError(f"unsupported source license for {case['id']}: {license_name}")
        destination = OUTPUT_DIR / f"{case['id']}.wav"
        duration = float(manifest["duration_seconds"])
        if not valid_audio(destination, duration):
            clip_audio(
                metadata["url"],
                destination,
                float(case["start_sec"]),
                duration,
                int(manifest["sample_rate"]),
            )
        provenance.append(
            {
                "id": case["id"],
                "source_title": case["source_title"],
                "source_page": metadata["description_url"],
                "license": license_name,
                "license_url": metadata["license_url"],
                "description": metadata["description"],
                "start_sec": case["start_sec"],
                "duration_seconds": manifest["duration_seconds"],
                "clip_sha256": sha256(destination),
            }
        )
        print(f"prepared {case['id']}: {license_name}")
    result = {"schema_version": 1, "cases": provenance}
    PROVENANCE_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def commons_metadata(title: str) -> dict[str, str]:
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "titles": title,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata",
            "format": "json",
            "formatversion": "2",
        }
    )
    response = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "5",
            "--retry-all-errors",
            "--retry-delay",
            "3",
            "--connect-timeout",
            "15",
            "--max-time",
            "120",
            "--user-agent",
            USER_AGENT,
            f"{COMMONS_API}?{query}",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=660,
    )
    payload = json.loads(response.stdout)
    page = payload["query"]["pages"][0]
    info = page["imageinfo"][0]
    extra = info["extmetadata"]
    return {
        "url": info["url"],
        "description_url": info["descriptionurl"],
        "license": extra["LicenseShortName"]["value"],
        "license_url": extra.get("LicenseUrl", {}).get("value", info["descriptionurl"]),
        "description": strip_html(extra.get("ImageDescription", {}).get("value", "")),
    }


def clip_audio(url: str, destination: Path, start: float, duration: float, rate: int) -> None:
    with tempfile.TemporaryDirectory(prefix="songdance-human-source-") as raw:
        source = Path(raw) / "source.media"
        subprocess.run(
            [
                "curl",
                "--location",
                "--fail",
                "--silent",
                "--show-error",
                "--retry",
                "5",
                "--retry-all-errors",
                "--retry-delay",
                "5",
                "--connect-timeout",
                "20",
                "--max-time",
                "300",
                "--user-agent",
                USER_AGENT,
                "--output",
                str(source),
                url,
            ],
            check=True,
            timeout=330,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(source),
                "-ss",
                str(start),
                "-t",
                str(duration),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(rate),
                "-c:a",
                "pcm_s16le",
                "-y",
                str(destination),
            ],
            check=True,
            timeout=180,
        )
    if not valid_audio(destination, duration):
        destination.unlink(missing_ok=True)
        raise RuntimeError("audio source did not produce the required duration")


def valid_audio(path: Path, duration: float) -> bool:
    if not path.is_file():
        return False
    try:
        with wave.open(str(path), "rb") as audio:
            actual_duration = audio.getnframes() / audio.getframerate()
    except (EOFError, wave.Error):
        return False
    return actual_duration >= duration - 0.1


def strip_html(value: str) -> str:
    import re

    return " ".join(re.sub(r"<[^>]+>", " ", value).split())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    prepare()
