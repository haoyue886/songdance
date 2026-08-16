import argparse
import hashlib
import json
import mimetypes
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

PACKAGE_ROOT = Path(__file__).resolve().parent


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


class ReviewHandler(BaseHTTPRequestHandler):
    package_root = PACKAGE_ROOT

    def do_POST(self) -> None:
        self._json(404, {"error": "offline review is screenshot-only"})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            html = (self.package_root / "index.html").read_text(encoding="utf-8")
            body = html.encode()
            self._send(200, "text/html; charset=utf-8", body)
            return
        if path.startswith("/files/"):
            self._serve_file(path.removeprefix("/files/"), self.package_root / "files")
            return
        if path.startswith("/piano/"):
            self._serve_file(path.removeprefix("/piano/"), self.package_root / "piano")
            return
        self._json(404, {"error": "not found"})

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
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

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
