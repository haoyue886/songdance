import argparse
import hashlib
import json
import mimetypes
import secrets
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

RATINGS = {"direct_use", "minor_edits", "needs_redo"}
PACKAGE_ROOT = Path(__file__).resolve().parent
MAX_BODY_BYTES = 64 * 1024


def verify_integrity(root: Path = PACKAGE_ROOT) -> dict[str, object]:
    manifest = _read_json(root / "integrity-manifest.json")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("离线包完整性清单无效")
    for relative, expected in files.items():
        target = _safe_target(root, str(relative))
        if not target.is_file() or _sha256(target) != expected:
            raise ValueError(f"离线包文件损坏或缺失：{relative}")
    review = _read_json(root / "files/structure-review.json")
    if review.get("suite_fingerprint") != manifest.get("suite_fingerprint"):
        raise ValueError("评审指纹与离线包不一致")
    return manifest


def save_review(payload: dict, root: Path = PACKAGE_ROOT) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("invalid review payload")
    if payload.get("midi_daw_experience") is not True:
        raise ValueError("请由具备 MIDI/DAW 使用经验的人完成评审")
    manifest = _read_json(root / "files/manifest.json")
    expected_ids = [case["id"] for case in manifest["cases"]]
    results = payload.get("results")
    if not isinstance(results, list) or any(
        not isinstance(case, dict) for case in results
    ):
        raise ValueError("请完成全部 16 段评级")
    if [case.get("id") for case in results] != expected_ids:
        raise ValueError("请完成全部 16 段评级")
    if any(case.get("rating") not in RATINGS for case in results):
        raise ValueError("请完成全部 16 段评级")
    source = _read_json(root / "files/structure-review.json")
    stored = {case["id"]: case for case in source["results"]}
    normalized = [
        {
            "id": case["id"],
            "raw_midi_note_count": stored[case["id"]]["raw_midi_note_count"],
            "parser_validation": stored[case["id"]]["parser_validation"],
            "rating": case["rating"],
            "notes": str(case.get("notes", ""))[:1000],
        }
        for case in results
    ]
    # The packaged server supports system Python 3.9, which has no datetime.UTC.
    source["reviewer"] = {
        "midi_daw_experience": True,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
    }
    source["results"] = normalized
    output = root / "completed-review.json"
    output.write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    usable = sum(case["rating"] != "needs_redo" for case in normalized)
    arpeggio = next(case for case in normalized if case["id"] == "04-arpeggios")
    arpeggio_passed = arpeggio["rating"] in {"direct_use", "minor_edits"}
    return {
        "usable_count": usable,
        "total_count": len(normalized),
        "arpeggio_passed": arpeggio_passed,
        "passed": usable >= source["minimum_readable_count"] and arpeggio_passed,
        "output": output.name,
    }


class ReviewHandler(BaseHTTPRequestHandler):
    token = secrets.token_urlsafe(24)
    package_root = PACKAGE_ROOT

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            html = (self.package_root / "index.html").read_text(encoding="utf-8")
            body = html.replace(
                "<body>", f'<body data-token="{self.token}">'
            ).encode()
            self._send(200, "text/html; charset=utf-8", body)
            return
        if path.startswith("/files/"):
            self._serve_file(path.removeprefix("/files/"), self.package_root / "files")
            return
        if path.startswith("/piano/"):
            self._serve_file(path.removeprefix("/piano/"), self.package_root / "piano")
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/review":
            self._json(404, {"error": "not found"})
            return
        if self.headers.get("X-Review-Token") != self.token:
            self._json(403, {"error": "invalid review token"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "invalid request size"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(400, {"error": "invalid request size"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
            outcome = save_review(payload, self.package_root)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._json(400, {"error": str(error)})
            return
        self._json(200, outcome)

    def _serve_file(self, raw_path: str, root: Path) -> None:
        try:
            target = _safe_target(root, unquote(raw_path))
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

    def _json(self, status: int, payload: dict[str, object]) -> None:
        self._send(
            status,
            "application/json",
            json.dumps(payload, ensure_ascii=False).encode(),
        )

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def run(root: Path = PACKAGE_ROOT, port: int = 8766, *, open_browser: bool = True) -> None:
    verify_integrity(root)
    ReviewHandler.package_root = root
    server = ThreadingHTTPServer(("127.0.0.1", port), ReviewHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"SongDance 离线结构评审：{url}")
    if open_browser:
        webbrowser.open(url)
    server.serve_forever()


def _safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError("invalid path") from error
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="SongDance 离线结构评审")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.check:
        manifest = verify_integrity()
        print(
            json.dumps(
                {
                    "status": "passed",
                    "suite_fingerprint": manifest["suite_fingerprint"],
                    "file_count": len(manifest["files"]),
                },
                ensure_ascii=False,
            )
        )
        return
    run(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
