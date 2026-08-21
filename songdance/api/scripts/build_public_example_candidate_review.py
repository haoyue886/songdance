"""Build a screenshot-only offline review package for one public-example candidate."""

# ruff: noqa: E501

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

API_ROOT = Path(__file__).parents[1]
CANDIDATE_ROOT = API_ROOT / "tests/fixtures/audio/public-example-candidates/petzold-minuet"
DEFAULT_OUTPUT = API_ROOT / "dist"
PACKAGE_NAME = "songdance-petzold-minuet-candidate-review"
FILES = (
    "candidate.json",
    "source.wav",
    "reference.mid",
    "reference.pdf",
    "raw.mid",
    "score.mid",
    "score.musicxml",
    "timeline.json",
)


def build_package(output_dir: Path = DEFAULT_OUTPUT) -> Path:
    candidate = _read_json(CANDIDATE_ROOT / "candidate.json")
    _require_pending_candidate(candidate)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{PACKAGE_NAME}.zip"
    with tempfile.TemporaryDirectory(prefix="songdance-petzold-review-") as raw:
        root = Path(raw) / PACKAGE_NAME
        files = root / "files"
        files.mkdir(parents=True)
        for filename in FILES:
            shutil.copy2(CANDIDATE_ROOT / filename, files / filename)
        (root / "index.html").write_text(_html(candidate), encoding="utf-8")
        (root / "README.md").write_text(_readme(candidate), encoding="utf-8")
        (root / "start-review.command").write_text(
            '#!/bin/sh\ncd "$(dirname "$0")"\npython3 -m http.server 8766 --bind 127.0.0.1\n',
            encoding="utf-8",
        )
        (root / "start-review.bat").write_text(
            "@echo off\r\ncd /d %~dp0\r\npython -m http.server 8766 --bind 127.0.0.1\r\n",
            encoding="utf-8",
        )
        (root / "start-review.command").chmod(0o755)
        integrity = {
            "schema_version": 1,
            "candidate_id": candidate["candidate_id"],
            "files": {
                path.relative_to(root).as_posix(): _sha256(path)
                for path in sorted(root.rglob("*"))
                if path.is_file()
            },
        }
        (root / "integrity-manifest.json").write_text(
            json.dumps(integrity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(PACKAGE_NAME) / path.relative_to(root))
    return destination


def _html(candidate: dict[str, object]) -> str:
    source = candidate["source"]
    reference = candidate["reference_score"]
    pipeline = candidate["pipeline"]
    analysis = pipeline["analysis"]
    notation = pipeline["notation"]
    parser = pipeline["parser_validation"]
    structure = pipeline["structure"]
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SongDance · Petzold 初级候选人工评审</title><style>
:root{{font-family:Inter,system-ui,sans-serif;color:#19231f;background:#f4f7f5}}*{{box-sizing:border-box}}body{{margin:0}}
header{{background:#193d35;color:#fff;padding:22px 24px}}h1{{font-size:22px;margin:0 0 6px}}header p{{margin:0;color:#dbe9e2;font-size:14px}}
main{{max-width:1060px;margin:24px auto;padding:0 18px 80px}}section{{background:#fff;border:1px solid #d7e2dc;border-radius:8px;padding:18px;margin:14px 0}}h2{{font-size:17px;margin:0 0 14px;color:#1f4037}}dl{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}}dt{{font-size:12px;color:#65766f;font-weight:700}}dd{{margin:4px 0 0;overflow-wrap:anywhere}}audio{{width:100%}}.links{{display:flex;flex-wrap:wrap;gap:9px}}a{{color:#075e55}}a.file{{display:inline-block;border:1px solid #b9cfc5;border-radius:6px;padding:8px 10px;text-decoration:none}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border-bottom:1px solid #e2ebe6;text-align:left;padding:8px 6px;vertical-align:top}}th{{color:#65766f;font-size:12px}}.warn{{border-left:4px solid #c47a25;background:#fff8ed;padding:12px}}.ratings{{display:flex;gap:10px;flex-wrap:wrap}}label{{border:1px solid #c7d5ce;border-radius:6px;padding:9px 12px}}textarea{{width:100%;min-height:90px;margin-top:12px;border:1px solid #c7d5ce;border-radius:6px;padding:10px;font:inherit}}.small{{font-size:13px;color:#65766f}}@media(max-width:700px){{dl{{grid-template-columns:1fr}}main{{padding:0 12px 60px}}}}
</style></head><body><header><h1>Christian Petzold · G大调小步舞曲 BWV Anh.114</h1><p>初级公开示例候选 · 当前状态：candidate_pending · 评审后请截图本页发回项目维护者</p></header>
<main><section><h2>原音与来源</h2><audio controls preload="metadata" src="files/source.wav"></audio><dl>
<div><dt>演奏者</dt><dd>{candidate['performer']}</dd></div><div><dt>录音片段</dt><dd>{source['clip_duration_sec']} 秒，起点 {source['clip_start_sec']} 秒</dd></div><div><dt>许可</dt><dd><a href="{source['license_url']}" target="_blank" rel="noreferrer">{source['license']}</a></dd></div></dl><p class="small">录音来源：<a href="{source['source_page']}" target="_blank" rel="noreferrer">Wikimedia Commons</a>。这是真人数字钢琴演奏，不是 MIDI 合成。</p></section>
<section><h2>参考谱与产物</h2><div class="links"><a class="file" href="files/reference.pdf">参考 PDF</a><a class="file" href="files/reference.mid">参考 MIDI</a><a class="file" href="files/raw.mid">Raw MIDI</a><a class="file" href="files/score.mid">量化 MIDI</a><a class="file" href="files/score.musicxml">MusicXML</a><a class="file" href="files/timeline.json">时间线 JSON</a></div><p class="small">参考来源：<a href="{reference['source_page']}" target="_blank" rel="noreferrer">Pianovera</a>，页面声明 MIDI/PDF 来自 Mutopia 公版编排。</p></section>
<section><h2>自动校验摘要</h2><table><tr><th>项目</th><th>结果</th><th>说明</th></tr><tr><td>参考谱</td><td>通过</td><td>{reference['parts']} 个声部，{reference['measure_count']} 小节，{reference['notation_key_signature'][0]}，{reference['time_signature'][0]}</td></tr><tr><td>音频分析</td><td>需人工关注</td><td>原始分析为 {analysis['time_signature']}（{analysis['time_signature_source']}），记谱按参考谱覆盖为 {notation['notation_time_signature']}</td></tr><tr><td>谱表结构</td><td>{structure.get('part_count')} part / {structure.get('staff_count')} staff</td><td>错误数 {len(structure.get('errors', []))}，休止符 {structure.get('rest_count')}</td></tr><tr><td>XML 解析</td><td>{parser['xmllint']['status']} / {parser['osmd']['status']}</td><td>OSMD 通过后才可进入公开示例发布判断</td></tr></table><div class="warn">候选尚未通过人工评级，也没有替换 K.545 失败对照。请重点检查：3/4 小节线、G 大调调号、低音谱表分配、重复音/休止符和漏音。</div></section>
<section><h2>人工评级</h2><div class="ratings"><label><input type="radio" name="rating"> 可直接使用</label><label><input type="radio" name="rating"> 少量修改可用</label><label><input type="radio" name="rating"> 需要重做</label></div><textarea placeholder="记录错音、漏音、拍号/小节线、左右手、休止符和踏板问题"></textarea><p class="small">此页面不保存评级。完成后请保留本页截图并发回项目维护者。</p></section></main></body></html>"""


def _readme(candidate: dict[str, object]) -> str:
    return f"""# SongDance Petzold 初级候选人工评审包

候选：`{candidate['candidate_id']}`

这是截图式评审包，不会提交评级。macOS 双击 `start-review.command`，或运行 `python3 -m http.server 8766 --bind 127.0.0.1`，然后打开 `http://127.0.0.1:8766`。

请对照原音、参考 PDF 和 MusicXML，选择评级并填写备注，完成后截图发回项目维护者。当前候选仍是 `candidate_pending`，不会替换 K.545 失败对照。
"""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _require_pending_candidate(candidate: dict[str, object]) -> None:
    if candidate.get("status") != "candidate_pending":
        raise ValueError("review package requires a candidate_pending manifest")
    review = candidate.get("review")
    if not isinstance(review, dict) or review.get("rating") != "pending":
        raise ValueError("review package requires a pending review rating")


if __name__ == "__main__":
    print(build_package())
