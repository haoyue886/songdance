from pathlib import Path

import pytest

from app.services.storage import LocalObjectStorage


def test_local_storage_rejects_path_escape(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path / "storage")
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")

    with pytest.raises(ValueError, match="escapes"):
        storage.put_file("../escaped.wav", source, "audio/wav")

    with pytest.raises(ValueError, match="escapes"):
        storage.exists("/tmp/escaped.wav")
