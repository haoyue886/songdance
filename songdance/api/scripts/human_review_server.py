# ruff: noqa: E501

import json
import mimetypes
import secrets
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import pretty_midi

from scripts.human_quality_gate import compute_suite_fingerprint
from scripts.prepare_human_regression_set import FIXTURE_ROOT

MANIFEST_PATH = FIXTURE_ROOT / "human-manifest.json"
REVIEW_PATH = FIXTURE_ROOT / "human-review.json"
PIANO_ASSET_ROOT = Path(__file__).parents[2] / "web/public/audio/piano"
MAX_BODY_BYTES = 64 * 1024
RATINGS = {"direct_use", "minor_edits", "needs_redo"}

HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SongDance 真人质量评审</title><style>
:root{font-family:Inter,system-ui,sans-serif;color:#191b1f;background:#f6f7f8}*{box-sizing:border-box}body{margin:0}
header{position:sticky;top:0;z-index:2;background:#fff;border-bottom:1px solid #dfe2e6;padding:16px 24px}h1{font-size:20px;margin:0 0 4px}header p{margin:0;color:#60656d;font-size:13px}
main{max-width:1040px;margin:24px auto;padding:0 20px 100px}.case{background:#fff;border:1px solid #dfe2e6;border-radius:8px;padding:18px;margin:12px 0;display:grid;gap:14px}
.case h2{font-size:16px;margin:0}.source{font-size:12px;color:#60656d;overflow-wrap:anywhere}.media{display:grid;grid-template-columns:1fr auto;gap:10px;align-items:center}audio{width:100%}
button,a.file{border:1px solid #b9bec6;background:#fff;color:#202329;border-radius:6px;padding:8px 11px;font:inherit;text-decoration:none;cursor:pointer}button:hover,a.file:hover{background:#f1f3f5}.files,.ratings{display:flex;gap:8px;flex-wrap:wrap}
.ratings label{border:1px solid #c8ccd2;border-radius:6px;padding:8px 10px;cursor:pointer}.ratings label:has(input:checked){border-color:#176b52;background:#eaf7f1}textarea{width:100%;min-height:58px;border:1px solid #c8ccd2;border-radius:6px;padding:9px;resize:vertical}
.save{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #dfe2e6;padding:14px 24px;display:flex;justify-content:center;gap:16px;align-items:center}.save button{background:#176b52;color:#fff;border-color:#176b52;font-weight:650}.error{color:#a33131}.ok{color:#176b52}
@media(max-width:600px){header{padding:14px 16px}main{padding:0 12px 100px}.media{grid-template-columns:1fr}.case{padding:14px}}
</style></head><body><header><h1>SongDance · 10 段真实钢琴质量评审</h1><p>逐段比较原音与转录；“少量修改”= 30 秒内不超过 10 个明显错音/漏音，且无需重建节拍网格。</p></header>
<main id="cases"></main><div class="save"><label><input id="experience" type="checkbox"> 我具备 MIDI/DAW 使用经验</label><button id="save">保存评审</button><span id="status"></span></div>
<script>
const sampleDefs=new Map([[21,'A0.mp3'],[24,'C1.mp3'],[27,'Ds1.mp3'],[30,'Fs1.mp3'],[33,'A1.mp3'],[36,'C2.mp3'],[39,'Ds2.mp3'],[42,'Fs2.mp3'],[45,'A2.mp3'],[48,'C3.mp3'],[51,'Ds3.mp3'],[54,'Fs3.mp3'],[57,'A3.mp3'],[60,'C4.mp3'],[63,'Ds4.mp3'],[66,'Fs4.mp3'],[69,'A4.mp3'],[72,'C5.mp3'],[75,'Ds5.mp3'],[78,'Fs5.mp3'],[81,'A5.mp3'],[84,'C6.mp3'],[87,'Ds6.mp3'],[90,'Fs6.mp3'],[93,'A6.mp3'],[96,'C7.mp3'],[99,'Ds7.mp3'],[102,'Fs7.mp3'],[105,'A7.mp3'],[108,'C8.mp3']]);
let pianoContext=null,pianoBuffers=null;const active=[]; const escapeHtml=s=>String(s).replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[c]));
async function init(){const [m,r]=await Promise.all([fetch('/files/human-manifest.json').then(x=>x.json()),fetch('/files/human-review.json').then(x=>x.json())]);
document.querySelector('#experience').checked=r.reviewer.midi_daw_experience===true;const prior=Object.fromEntries(r.results.map(x=>[x.id,x]));
document.querySelector('#cases').innerHTML=m.cases.map((c,i)=>{const p=prior[c.id]||{rating:'pending',notes:''},source=c.source_title||c.description||c.id,coverage=c.coverage||[c.pattern||''];return `<section class="case" data-id="${c.id}"><h2>${i+1}. ${escapeHtml(c.id)}</h2><div class="source">${escapeHtml(source)} · ${escapeHtml(coverage.join(' / '))}</div><div class="media"><audio controls preload="metadata" src="/files/human-generated/${c.id}.wav"></audio><button type="button" onclick="playTimeline('${c.id}',this)">播放转录</button></div><div class="files"><a class="file" href="/files/human-review-artifacts/${c.id}/raw.mid">Raw MIDI</a><a class="file" href="/files/human-review-artifacts/${c.id}/score.mid">量化 MIDI</a><a class="file" href="/files/human-review-artifacts/${c.id}/score.musicxml">MusicXML</a></div><div class="ratings">${[['direct_use','可直接使用'],['minor_edits','少量修改可用'],['needs_redo','需要重做']].map(([v,l])=>`<label><input type="radio" name="${c.id}" value="${v}" ${p.rating===v?'checked':''}> ${l}</label>`).join('')}</div><textarea aria-label="评审备注" placeholder="错音、漏音、节拍或分手问题">${escapeHtml(p.notes)}</textarea></section>`}).join('');}
async function loadPiano(){pianoContext||=new AudioContext();await pianoContext.resume();if(!pianoBuffers){const entries=await Promise.all([...sampleDefs].map(async([midi,file])=>{const response=await fetch(`/piano/${file}`);if(!response.ok)throw new Error('钢琴采样加载失败');return [midi,await pianoContext.decodeAudioData(await response.arrayBuffer())]}));pianoBuffers=new Map(entries)}return [pianoContext,pianoBuffers]}
function nearestSample(pitch){return [...sampleDefs.keys()].reduce((best,value)=>Math.abs(value-pitch)<Math.abs(best-pitch)?value:best,21)}
async function playTimeline(id,button){stopPlayback();button.textContent='加载钢琴音色…';try{const [ctx,buffers]=await loadPiano();const data=await fetch(`/files/human-review-artifacts/${id}/timeline.json`).then(x=>x.json());const start=ctx.currentTime+.08;for(const n of data.notation_notes||data.notes){const base=nearestSample(n.pitch),source=ctx.createBufferSource(),gain=ctx.createGain();source.buffer=buffers.get(base);source.playbackRate.value=Math.pow(2,(n.pitch-base)/12);gain.gain.value=.14*Math.max(.2,n.velocity/127);source.connect(gain).connect(ctx.destination);source.start(start+n.start_sec);source.stop(start+n.end_sec);active.push(source)}button.textContent='播放中';setTimeout(()=>{button.textContent='播放转录';stopPlayback()},31000)}catch(error){button.textContent='播放转录';document.querySelector('#status').className='error';document.querySelector('#status').textContent=error.message}}
function stopPlayback(){while(active.length){try{active.pop().stop()}catch{}}}
document.querySelector('#save').onclick=async()=>{const status=document.querySelector('#status');const sections=[...document.querySelectorAll('.case')];const results=sections.map(s=>({id:s.dataset.id,rating:s.querySelector('input:checked')?.value||'pending',notes:s.querySelector('textarea').value.trim()}));try{const response=await fetch('/review',{method:'POST',headers:{'Content-Type':'application/json','X-Review-Token':document.body.dataset.token||''},body:JSON.stringify({midi_daw_experience:document.querySelector('#experience').checked,results})});const data=await response.json();if(!response.ok)throw new Error(data.error);status.className='ok';status.textContent=`已保存：${data.usable_count}/${data.total_count} 可用`;}catch(e){status.className='error';status.textContent=e.message}};
init().catch(e=>{document.querySelector('#status').className='error';document.querySelector('#status').textContent=e.message});
</script></body></html>"""


class ReviewHandler(BaseHTTPRequestHandler):
    token = secrets.token_urlsafe(24)
    html = HTML

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            body = self.html.replace("<body>", f'<body data-token="{self.token}">').encode()
            self._send(200, "text/html; charset=utf-8", body)
            return
        if path.startswith("/files/"):
            self._serve_file(path.removeprefix("/files/"))
            return
        if path.startswith("/piano/"):
            self._serve_piano(path.removeprefix("/piano/"))
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/review":
            self._json(404, {"error": "not found"})
            return
        if self.headers.get("X-Review-Token") != self.token:
            self._json(403, {"error": "invalid review token"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(400, {"error": "invalid request size"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            result = self._save_review(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
            return
        self._json(200, result)

    def _save_review(self, payload: dict) -> dict:
        return save_review(payload)

    def _serve_file(self, raw_path: str) -> None:
        self._serve_root_file(raw_path, FIXTURE_ROOT)

    def _serve_piano(self, raw_path: str) -> None:
        self._serve_root_file(raw_path, PIANO_ASSET_ROOT)

    def _serve_root_file(self, raw_path: str, root: Path) -> None:
        target = (root / unquote(raw_path)).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            self._json(403, {"error": "invalid path"})
            return
        if not target.is_file():
            self._json(404, {"error": "not found"})
            return
        self._send(
            200,
            mimetypes.guess_type(target.name)[0] or "application/octet-stream",
            target.read_bytes(),
        )

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, "application/json", json.dumps(payload, ensure_ascii=False).encode())

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def save_review(payload: dict) -> dict:
    if payload.get("midi_daw_experience") is not True:
        raise ValueError("请由具备 MIDI/DAW 使用经验的人完成评审")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = [case["id"] for case in manifest["cases"]]
    results = payload["results"]
    if [case.get("id") for case in results] != expected:
        raise ValueError("评审项目与固定测试集不一致")
    if any(case.get("rating") not in RATINGS for case in results):
        raise ValueError("请完成全部 10 段评级")
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    fingerprint = compute_suite_fingerprint(FIXTURE_ROOT)
    if review.get("suite_fingerprint") != fingerprint:
        raise ValueError("回归产物已变化，请重新生成测试集后再评审")
    raw_note_counts = {case["id"]: case.get("raw_midi_note_count") for case in review["results"]}
    normalized = [
        {
            "id": case["id"],
            "raw_midi_note_count": _preserved_or_recovered_note_count(
                case["id"], raw_note_counts.get(case["id"])
            ),
            "rating": case["rating"],
            "notes": str(case.get("notes", ""))[:1000],
        }
        for case in results
    ]
    review["reviewer"] = {"midi_daw_experience": True, "reviewed_at": datetime.now(UTC).isoformat()}
    review["results"] = normalized
    REVIEW_PATH.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    usable = sum(case["rating"] != "needs_redo" for case in normalized)
    return {"usable_count": usable, "total_count": len(normalized), "passed": usable >= 7}


def _raw_midi_note_count(case_id: str) -> int:
    raw_midi = FIXTURE_ROOT / "human-review-artifacts" / case_id / "raw.mid"
    try:
        parsed = pretty_midi.PrettyMIDI(str(raw_midi))
    except Exception as error:
        raise ValueError(f"无法恢复 {case_id} 的原始 MIDI 音符数") from error
    count = sum(len(instrument.notes) for instrument in parsed.instruments)
    if count <= 0:
        raise ValueError(f"{case_id} 的原始 MIDI 不包含音符")
    return count


def _preserved_or_recovered_note_count(case_id: str, stored_count: object) -> int:
    if type(stored_count) is int and stored_count > 0:
        return stored_count
    return _raw_midi_note_count(case_id)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8765), ReviewHandler)
    print("SongDance human review: http://127.0.0.1:8765")
    server.serve_forever()
