import hashlib
import sys
import time
import urllib.request
from pathlib import Path

COMMIT = "a1ab73fc901d1759ec3bc173c146b3c6a3040261"
RAW_ROOT = f"https://raw.githubusercontent.com/EleutherAI/aria-amt/{COMMIT}"
FILES = {
    "amt/__init__.py": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
    "amt/audio.py": "5fa796a3a707334433948e3099f694a50230c60a",
    "amt/config.py": "8295bcab35d89af415445da6003f7201b0dd1cce",
    "amt/data.py": "2638636e7e130d4b45411b8178b849cc1cc972ed",
    "amt/inference/__init__.py": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
    "amt/inference/model.py": "6b0d6b50305a1be724e088a1281c3d17096e45e6",
    "amt/inference/quantize.py": "29088b1df13c3af782944f97f2bc554bc7effc08",
    "amt/inference/transcribe.py": "fd000b83551670bf6e374e274416a520ac43a0b1",
    "amt/mir.py": "8693eb85067705468c236b745ce1b83cba1013b9",
    "amt/model.py": "89b4da04a2770b85e1bf19be941372617d5c5c86",
    "amt/run.py": "7c3d26678088fade6c6cb39ac0c362f5cd9fcfdf",
    "amt/tokenizer.py": "da21fc81b1398c0008e0e16eaf9ac6e0c2deee38",
    "amt/train.py": "119b2ccb02f01743051c1f6dd04779e8de826bc9",
    "amt/utils.py": "2bc369d4b9cbdd8f6ba94bc35cb06b1b7516420b",
    "config/config.json": "d2c24a0303b0f9b296b8d4bf8aa279106d4dc544",
    "config/models/medium-double.json": "0cf3a518480aa31f537710f91b086445cc4913fc",
    "config/models/medium-single.json": "a0b38574ec832db724c8c3b29e4eff8d819391ef",
    "config/models/medium-triple.json": "463f65df108126a4b3accea71bb63cc67ad45d9c",
    "pyproject.toml": "a36856f6a20266b0424840d3ee1fe9314c229ba5",
}


def git_blob_sha1(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return hashlib.sha1(header + content, usedforsecurity=False).hexdigest()


def fetch(destination: Path) -> None:
    for relative_path, expected_sha1 in FILES.items():
        content = download(f"{RAW_ROOT}/{relative_path}")
        actual_sha1 = git_blob_sha1(content)
        if actual_sha1 != expected_sha1:
            raise ValueError(
                f"Git blob checksum mismatch for {relative_path}: {actual_sha1}"
            )
        output_path = destination / relative_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(content)


def download(url: str) -> bytes:
    for attempt in range(10):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == 9:
                raise
            time.sleep(min(2**attempt, 10))
    raise AssertionError("unreachable")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: fetch_pinned_source.py DESTINATION")
    fetch(Path(sys.argv[1]))
