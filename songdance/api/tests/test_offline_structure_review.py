import json
import shutil
import subprocess
import sys
import threading
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import scripts.build_offline_structure_review as offline_builder
import scripts.offline_structure_review_server as offline_server
from scripts.build_offline_structure_review import build_package
from scripts.offline_structure_review_server import (
    ReviewHandler,
    ThreadingHTTPServer,
)


@pytest.fixture(scope="module")
def package_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, Path]:
    output = tmp_path_factory.mktemp("offline-review")
    package = build_package(output)
    with zipfile.ZipFile(package) as archive:
        roots = {Path(name).parts[0] for name in archive.namelist()}
        assert len(roots) == 1
        package_root = output / roots.pop()
        archive.extractall(output)
    return package, package_root


@contextmanager
def _running_server(root: Path) -> Iterator[int]:
    ReviewHandler.package_root = root
    server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def _request(
    port: int,
    method: str,
    path: str,
    *,
    body: bytes | str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    connection = HTTPConnection("127.0.0.1", port)
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    result = response.status, response.read()
    connection.close()
    return result


def test_template_mismatch_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(offline_builder, "HTML", "unexpected template")
    with pytest.raises(ValueError, match="HTML 模板"):
        offline_builder._offline_html()


@pytest.mark.parametrize("failure_point", ["headers", "body"])
def test_server_ignores_client_disconnect(failure_point: str) -> None:
    handler = object.__new__(ReviewHandler)
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock()
    handler.wfile = Mock()
    if failure_point == "headers":
        handler.end_headers.side_effect = BrokenPipeError
    else:
        handler.wfile.write.side_effect = ConnectionResetError

    handler._send(200, "text/plain", b"review")


def test_offline_structure_review_package_is_complete_and_self_verifying(
    package_bundle: tuple[Path, Path],
) -> None:
    package, package_root = package_bundle

    assert package.is_file()
    manifest = json.loads(
        (package_root / "integrity-manifest.json").read_text(encoding="utf-8")
    )
    assert len(list((package_root / "files/generated").glob("*.wav"))) == 16
    artifacts = package_root / "files/structure-review-artifacts"
    for filename in ("raw.mid", "score.mid", "score.musicxml", "timeline.json"):
        assert len(list(artifacts.glob(f"*/{filename}"))) == 16
    assert len(list((package_root / "piano").glob("*.mp3"))) == 30
    for filename in (
        "README.md",
        "index.html",
        "review.py",
        "start-review.command",
        "start-review.bat",
    ):
        assert (package_root / filename).is_file()
    html = (package_root / "index.html").read_text(encoding="utf-8")
    assert "04-arpeggios 必须至少为少量修改可用" in html
    assert "评审完成后请截图此页面并发回项目维护者" in html
    assert "我具备 MIDI/DAW 使用经验" not in html
    assert "保存评审" not in html
    assert "fetch('/review'" not in html
    assert "Python 3.9 或更高版本" in (package_root / "README.md").read_text(
        encoding="utf-8"
    )
    with zipfile.ZipFile(package) as archive:
        command = next(
            info for info in archive.infolist() if info.filename.endswith(".command")
        )
        assert command.external_attr >> 16 & 0o111
    assert manifest["suite_fingerprint"][:12] in package.name
    system_python = shutil.which("python3") or sys.executable
    checked = subprocess.run(
        [system_python, "review.py", "--check"],
        cwd=package_root,
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(checked.stdout) == {
        "status": "passed",
        "suite_fingerprint": manifest["suite_fingerprint"],
        "file_count": len(manifest["files"]),
    }

def test_server_enforces_local_http_contract(
    package_bundle: tuple[Path, Path],
) -> None:
    _, package_root = package_bundle
    with _running_server(package_root) as port:
        status, raw_midi = _request(
            port,
            "GET",
            "/files/structure-review-artifacts/04-arpeggios/raw.mid",
        )
        assert status == 200
        assert raw_midi.startswith(b"MThd")
        assert _request(port, "GET", "/files/%2e%2e/review.py")[0] == 403
        assert _request(port, "POST", "/review", body=b"{}")[0] == 404


def test_run_binds_only_to_loopback(
    package_bundle: tuple[Path, Path],
) -> None:
    _, package_root = package_bundle
    with patch.object(offline_server, "ThreadingHTTPServer") as server_class:
        offline_server.run(package_root, port=43210, open_browser=False)

    server_class.assert_called_once_with(
        ("127.0.0.1", 43210), offline_server.ReviewHandler
    )
    server_class.return_value.serve_forever.assert_called_once_with()
