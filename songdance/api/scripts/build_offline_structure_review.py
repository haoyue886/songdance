import argparse
import base64
import hashlib
import json
import shutil
import subprocess
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
        subprocess.run(
            ["node", str(API_ROOT.parent / "web/scripts/render-review-pdfs.mjs"), str(files / "structure-review-artifacts")],
            cwd=API_ROOT.parent / "web",
            check=True,
        )
        shutil.copytree(PIANO_ROOT, root / "piano")
        (root / "standalone.html").write_text(
            _standalone_html(_read_json(MANIFEST_PATH), files / "structure-review-artifacts", root / "piano"),
            encoding="utf-8",
        )
        shutil.copy2(SERVER_SOURCE, root / "review.py")
        (root / "index.html").write_text(_offline_html(), encoding="utf-8")
        (root / "README.md").write_text(_readme(fingerprint), encoding="utf-8")
        (root / "start-review.command").write_text(
            '#!/bin/sh\n'
            'cd "$(dirname "$0")"\n'
            'if ! command -v python3 >/dev/null 2>&1; then\n'
            '  echo "未找到 Python 3。请安装 Python 3.9 或更高版本后重试。"\n'
            '  read -r _\n'
            '  exit 1\n'
            'fi\n'
            'python3 review.py --check || { echo "评审包完整性检查失败。"; read -r _; exit 1; }\n'
            'python3 review.py\n'
            'status=$?\n'
            'echo "评审服务已停止，按回车关闭窗口。"\n'
            'read -r _\n'
            'exit "$status"\n', encoding="utf-8"
        )
        (root / "start-review.bat").write_text(
            "@echo off\r\n"
            "cd /d %~dp0\r\n"
            "set PYTHON_CMD=\r\n"
            "where py >nul 2>nul && set PYTHON_CMD=py -3\r\n"
            "if not defined PYTHON_CMD where python >nul 2>nul && set PYTHON_CMD=python\r\n"
            "if not defined PYTHON_CMD (\r\n"
            "  echo 未找到 Python 3。\r\n"
            "  echo 请打开 https://www.python.org/downloads/windows/ 安装 Python 3.9 或更高版本。\r\n"
            "  echo 安装时务必勾选 Add Python to PATH，然后重新双击本文件。\r\n"
            "  pause\r\n"
            "  exit /b 1\r\n"
            ")\r\n"
            "%PYTHON_CMD% review.py --check || (echo 评审包完整性检查失败。& pause& exit /b 1)\r\n"
            "%PYTHON_CMD% review.py\r\n"
            "pause\r\n", encoding="utf-8"
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
    rendered = _replace_once(
        HTML,
        "SongDance · Phase 15 结构谱面评审",
        "SongDance · Phase 30 离线结构谱面复评",
    )
    rendered = _replace_once(
        rendered,
        "逐段检查节拍、和弦、声部、左右手和小节排版；"
        "至少 13/16 段需达到可直接使用或少量修改可用。",
        "逐段检查节拍、和弦、声部、左右手和小节排版；"
        "至少 13/16 段可用，04-arpeggios 必须至少为少量修改可用。",
    )
    rendered = _replace_once(
        rendered,
        '<main id="cases"></main><div class="save"><label><input '
        'id="experience" type="checkbox"> 我具备 MIDI/DAW 使用经验</label>'
        '<button id="save">保存评审</button><span id="status"></span></div>',
        '<main id="cases"></main><div class="save"><span id="status">'
        '评审完成后请截图此页面并发回项目维护者。</span></div>',
    )
    rendered = _replace_once(
        rendered,
        "document.querySelector('#experience').checked="
        "r.reviewer.midi_daw_experience===true;",
        "",
    )
    return _remove_section(
        rendered,
        "document.querySelector('#save').onclick=",
        "init().catch",
    )


def _replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError("离线评审 HTML 模板与基础页面不一致")
    return source.replace(old, new, 1)


def _remove_section(source: str, start: str, end: str) -> str:
    before, found_start, remainder = source.partition(start)
    _, found_end, after = remainder.partition(end)
    if not found_start or not found_end:
        raise ValueError("离线评审 HTML 模板与基础页面不一致")
    return before + end + after


def _readme(fingerprint: str) -> str:
    return f"""# SongDance Phase 30 离线结构谱面复评

固定集指纹：`{fingerprint}`

## 启动

- 需要 Python 3.9 或更高版本，不需要安装第三方依赖。
- macOS：双击 `start-review.command`，或运行 `python3 review.py`。
- Windows：双击 `start-review.bat`，或运行 `py -3 review.py`。如果提示未找到 Python，请打开 `https://www.python.org/downloads/windows/` 安装 Python 3.9 或更高版本；安装时勾选 **Add Python to PATH**，安装完成后重新双击启动脚本。
- 无需安装：直接双击 `standalone.html`，不需要 Python；该入口支持原音播放、PDF/MusicXML/MIDI 下载和评审备注，完成后截图发回项目维护者。
- 浏览器会打开 `http://127.0.0.1:8766`，全程只访问本机文件。
- 逐段播放音频或转录，选择评级并填写备注；完成后直接截图页面发回项目维护者。

## 评级门槛

- 请完成全部 16 段评级，截图中保留段落编号、评级和备注。
- 至少 13/16 段为“可直接使用”或“少量修改可用”。
- `04-arpeggios` 必须至少为“少量修改可用”。
- 项目维护者会根据截图录入正式评级。

运行 `python3 review.py --check` 可验证包内所有文件的 SHA-256 完整性。
"""


def _standalone_html(manifest: dict, artifact_root: Path, piano_root: Path) -> str:
    cases = json.dumps(manifest.get("cases", []), ensure_ascii=False)
    timelines = {case["id"]: json.loads((artifact_root / case["id"] / "timeline.json").read_text(encoding="utf-8")) for case in manifest.get("cases", [])}
    sample_names = ["A0", "C1", "Ds1", "Fs1", "A1", "C2", "Ds2", "Fs2", "A2", "C3", "Ds3", "Fs3", "A3", "C4", "Ds4", "Fs4", "A4", "C5", "Ds5", "Fs5", "A5", "C6", "Ds6", "Fs6", "A6", "C7", "Ds7", "Fs7", "A7", "C8"]
    sample_midis = [21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72, 75, 78, 81, 84, 87, 90, 93, 96, 99, 102, 105, 108]
    samples = {str(midi): "data:audio/mpeg;base64," + base64.b64encode((piano_root / f"{name}.mp3").read_bytes()).decode("ascii") for midi, name in zip(sample_midis, sample_names)}
    return f'''<!doctype html><meta charset="utf-8"><title>SongDance 离线谱面评审</title>
<style>body{{font:16px system-ui,sans-serif;max-width:980px;margin:32px auto;padding:0 16px;color:#20252b}}section{{border:1px solid #d8dde3;border-radius:8px;padding:16px;margin:16px 0}}a,button{{display:inline-block;margin:6px 6px 6px 0;padding:8px 10px;border:1px solid #b9c2cc;border-radius:5px;background:#fff;color:#165b46;text-decoration:none;cursor:pointer}}textarea{{display:block;width:100%;min-height:60px;margin-top:10px}}.rating label{{margin-right:12px}}.hint{{color:#59636e}}</style>
<h1>SongDance 离线谱面评审</h1><p class="hint">无需 Python。播放原音和转录音，对照 PDF 乐谱，选择评级并填写备注。完成后截图发回项目维护者。</p><main id="cases"></main>
<script>const cases={cases};const timelines={json.dumps(timelines,ensure_ascii=False)};const samples={json.dumps(samples)};let active=[];function stop(){{active.forEach(x=>{{try{{x.stop()}}catch{{}}}});active=[]}}async function play(id,button){{stop();button.textContent='加载转录音…';try{{const ctx=new AudioContext();await ctx.resume();const buffers=new Map();for(const [pitch,url] of Object.entries(samples)){{const response=await fetch(url);buffers.set(pitch,await ctx.decodeAudioData(await response.arrayBuffer()))}}const nearest=p=>Object.keys(samples).reduce((a,b)=>Math.abs(+b-p)<Math.abs(+a-p)?b:a);const start=ctx.currentTime+.05;for(const n of (timelines[id].notation_notes||timelines[id].notes||[])){{const base=nearest(n.pitch),source=ctx.createBufferSource(),gain=ctx.createGain();source.buffer=buffers.get(base);source.playbackRate.value=Math.pow(2,(n.pitch-base)/12);gain.gain.value=.14*Math.max(.2,n.velocity/127);source.connect(gain).connect(ctx.destination);source.start(start+n.start_sec);source.stop(start+n.end_sec);active.push(source)}}button.textContent='停止转录音';button.onclick=()=>{{stop();button.textContent='播放转录音';button.onclick=()=>play(id,button)}}}}catch(error){{button.textContent='播放失败：'+error.message}}}}document.querySelector('#cases').innerHTML=cases.map((c,i)=>{{const id=encodeURIComponent(c.id);return `<section><h2>${{i+1}}. ${{c.id}}</h2><audio controls preload="metadata" src="files/generated/${{id}}.wav"></audio><div><button type="button" onclick="play('${{c.id}}',this)">播放转录音</button><a href="files/structure-review-artifacts/${{id}}/score.pdf" download>下载 PDF 乐谱</a><a href="files/structure-review-artifacts/${{id}}/score.musicxml">MusicXML</a><a href="files/structure-review-artifacts/${{id}}/score.mid">量化 MIDI</a></div><div class="rating"><label><input type="radio" name="${{id}}" value="direct_use"> 可直接使用</label><label><input type="radio" name="${{id}}" value="minor_edits"> 少量修改可用</label><label><input type="radio" name="${{id}}" value="needs_redo"> 需要重做</label></div><textarea placeholder="错音、漏音、节拍、左右手或谱面问题"></textarea></section>`}}).join('');</script>'''


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
