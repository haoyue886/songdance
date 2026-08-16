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
from unittest.mock import patch

import pytest

import scripts.offline_structure_review_server as offline_server
from scripts.build_offline_structure_review import build_package
from scripts.offline_structure_review_server import (
    MAX_BODY_BYTES,
    ReviewHandler,
    ThreadingHTTPServer,
    save_review,
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

    review = json.loads(
        (package_root / "files/structure-review.json").read_text(encoding="utf-8")
    )
    results = [
        {
            "id": case["id"],
            "rating": "minor_edits" if index < 13 else "needs_redo",
            "notes": "offline verified",
        }
        for index, case in enumerate(review["results"])
    ]
    payload = {"midi_daw_experience": True, "results": results}
    assert save_review(payload, package_root) == {
        "usable_count": 13,
        "total_count": 16,
        "arpeggio_passed": True,
        "passed": True,
        "output": "completed-review.json",
    }
    assert (package_root / "completed-review.json").is_file()

    results[3]["rating"] = "needs_redo"
    results[13]["rating"] = "minor_edits"
    assert save_review(payload, package_root)["passed"] is False
    with pytest.raises(ValueError, match="MIDI/DAW"):
        save_review({**payload, "midi_daw_experience": False}, package_root)


def test_server_rejects_malformed_content_length(
    package_bundle: tuple[Path, Path],
) -> None:
    _, package_root = package_bundle
    with _running_server(package_root) as port:
        connection = HTTPConnection("127.0.0.1", port)
        connection.putrequest("POST", "/review")
        connection.putheader("X-Review-Token", ReviewHandler.token)
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", "abc")
        connection.endheaders()
        response = connection.getresponse()

    assert response.status == 400
    assert json.loads(response.read())["error"] == "invalid request size"


def test_server_rejects_non_object_json(
    package_bundle: tuple[Path, Path],
) -> None:
    _, package_root = package_bundle
    with _running_server(package_root) as port:
        connection = HTTPConnection("127.0.0.1", port)
        connection.request(
            "POST",
            "/review",
            body="[]",
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": ReviewHandler.token,
            },
        )
        response = connection.getresponse()

    assert response.status == 400
    assert json.loads(response.read())["error"] == "invalid review payload"


def test_server_rejects_non_object_result(
    package_bundle: tuple[Path, Path],
) -> None:
    _, package_root = package_bundle
    with _running_server(package_root) as port:
        status, body = _request(
            port,
            "POST",
            "/review",
            body=json.dumps(
                {"midi_daw_experience": True, "results": [1]}
            ),
            headers={
                "Content-Type": "application/json",
                "X-Review-Token": ReviewHandler.token,
            },
        )

    assert status == 400
    assert json.loads(body)["error"] == "请完成全部 16 段评级"


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
        assert _request(port, "POST", "/review", body=b"{}")[0] == 403
        headers = {
            "Content-Type": "application/json",
            "X-Review-Token": ReviewHandler.token,
        }
        assert (
            _request(
                port,
                "POST",
                "/review",
                body=b"x" * (MAX_BODY_BYTES + 1),
                headers=headers,
            )[0]
            == 400
        )
        review = json.loads(
            (package_root / "files/structure-review.json").read_text(encoding="utf-8")
        )
        payload = {
            "midi_daw_experience": True,
            "results": [
                {"id": case["id"], "rating": "minor_edits", "notes": "test only"}
                for case in review["results"]
            ],
        }
        status, body = _request(
            port,
            "POST",
            "/review",
            body=json.dumps(payload),
            headers=headers,
        )

    assert status == 200
    assert json.loads(body)["passed"] is True
    assert (package_root / "completed-review.json").is_file()


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
