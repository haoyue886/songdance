import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from scripts.structure_quality_gate import (
    ARTIFACT_ROOT,
    GENERATED_ROOT,
    MANIFEST_PATH,
    REVIEW_PATH,
)
from scripts.structure_review_server import HTML

API_ROOT = Path(__file__).parents[1]
PIANO_ROOT = API_ROOT.parent / "web/public/audio/piano"
SERVER_SOURCE = Path(__file__).with_name("offline_structure_review_server.py")
DEFAULT_OUTPUT = API_ROOT / "dist"


def build_package(output_dir: Path = DEFAULT_OUTPUT) -> Path:
    review = _read_json(REVIEW_PATH)
    fingerprint = review.get("suite_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ValueError("结构评审指纹不可用，请先重新生成固定集")
    package_name = f"songdance-structure-review-{fingerprint[:12]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{package_name}.zip"
    with tempfile.TemporaryDirectory(prefix="songdance-offline-review-") as raw:
        root = Path(raw) / package_name
        files = root / "files"
        files.mkdir(parents=True)
        shutil.copy2(MANIFEST_PATH, files / "manifest.json")
        shutil.copy2(REVIEW_PATH, files / "structure-review.json")
        shutil.copytree(GENERATED_ROOT, files / "generated")
        shutil.copytree(ARTIFACT_ROOT, files / "structure-review-artifacts")
        shutil.copytree(PIANO_ROOT, root / "piano")
        shutil.copy2(SERVER_SOURCE, root / "review.py")
        (root / "index.html").write_text(_offline_html(), encoding="utf-8")
        (root / "README.md").write_text(_readme(fingerprint), encoding="utf-8")
        (root / "start-review.command").write_text(
            '#!/bin/sh\ncd "$(dirname "$0")"\npython3 review.py\n', encoding="utf-8"
        )
        (root / "start-review.bat").write_text(
            "@echo off\r\ncd /d %~dp0\r\npython review.py\r\n", encoding="utf-8"
        )
        (root / "start-review.command").chmod(0o755)
        integrity = {
            "schema_version": 1,
            "suite_fingerprint": fingerprint,
            "files": {
                path.relative_to(root).as_posix(): _sha256(path)
                for path in sorted(root.rglob("*"))
                if path.is_file()
            },
        }
        (root / "integrity-manifest.json").write_text(
            json.dumps(integrity, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(package_name) / path.relative_to(root))
    return destination


def _offline_html() -> str:
    return (
        HTML.replace(
            "SongDance · Phase 15 结构谱面评审",
            "SongDance · Phase 30 离线结构谱面复评",
        )
        .replace(
            "逐段检查节拍、和弦、声部、左右手和小节排版；"
            "至少 13/16 段需达到可直接使用或少量修改可用。",
            "逐段检查节拍、和弦、声部、左右手和小节排版；"
            "至少 13/16 段可用，04-arpeggios 必须至少为少量修改可用。",
        )
        .replace(
            "已保存：${data.usable_count}/${data.total_count} 可用",
            "已保存 completed-review.json：${data.usable_count}/${data.total_count} 可用",
        )
    )


def _readme(fingerprint: str) -> str:
    return f"""# SongDance Phase 30 离线结构谱面复评

固定集指纹：`{fingerprint}`

## 启动

- 需要 Python 3.9 或更高版本，不需要安装第三方依赖。
- macOS：双击 `start-review.command`，或运行 `python3 review.py`。
- Windows：双击 `start-review.bat`，或运行 `python review.py`。
- 浏览器会打开 `http://127.0.0.1:8766`，全程只访问本机文件。

## 评级门槛

- 必须由具备 MIDI/DAW 使用经验的人完成全部 16 段。
- 至少 13/16 段为“可直接使用”或“少量修改可用”。
- `04-arpeggios` 必须至少为“少量修改可用”。
- 保存后会在本目录生成 `completed-review.json`，请将该文件交回项目维护者。

运行 `python3 review.py --check` 可验证包内所有文件的 SHA-256 完整性。
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 SongDance 离线结构评审包")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(build_package(args.output_dir))


if __name__ == "__main__":
    main()
