import json

import pytest

from scripts.build_repeat_annotation_page import build
from scripts.piano_comparison_cases import file_sha256


def fixture(tmp_path):
    (tmp_path / "clip.wav").write_bytes(b"fixture")
    manifest = {
        "candidates": [{"clip_file": "clip.wav", "clip_sha256": file_sha256(tmp_path / "clip.wav")}]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    labels = {
        "manifest_sha256": file_sha256(tmp_path / "manifest.json"),
        "reviewer": "</script><script>bad()</script>",
    }
    (tmp_path / "labels.json").write_text(json.dumps(labels))


def test_build_escapes_embedded_data_and_refuses_overwrite(tmp_path):
    fixture(tmp_path)
    path = build(tmp_path)
    assert "</script><script>bad()" not in path.read_text()
    assert "\\u003c/script>" in path.read_text()
    with pytest.raises(FileExistsError):
        build(tmp_path)


def test_changed_clip_rejected(tmp_path):
    fixture(tmp_path)
    (tmp_path / "clip.wav").write_bytes(b"changed")
    with pytest.raises(ValueError, match="clip"):
        build(tmp_path)
