import shutil
from pathlib import Path

import pytest

from scripts import probe_long_audio_limits as probe_module


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is required for real probing")
def test_probe_decodes_real_wav_and_reports_current_long_audio_rejections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SONGDANCE_MAX_REQUEST_BYTES", "1")
    monkeypatch.setenv("SONGDANCE_DATABASE_URL", "intentionally-invalid")
    report = probe_module.probe([90, 300])
    short, long = report["cases"]
    assert short["decoded_seconds"] == 90
    assert short["file_limit_allows"] is True
    assert short["clip_validation_error"] is None
    assert long["decoded_seconds"] == 300
    assert long["wav_bytes"] == 26_460_044
    assert long["file_limit_allows"] is False
    assert long["clip_validation_error"] == "INVALID_CLIP"
    assert long["analysis_window_covers_duration"] is False
    assert report["production_ready"] is False
    assert report["browser_upload_tested"] is False
    assert report["human_quality_tested"] is False
    assert report["limits"]["declared_request_body_bytes"] == 26 * 1024 * 1024
    assert all(len(value) == 64 for value in report["source_sha256"].values())


@pytest.mark.parametrize("durations", [[], [0], [-1], [601], [True], [1.5], [1] * 13])
def test_probe_rejects_unbounded_or_invalid_work(durations: list[int]) -> None:
    with pytest.raises(ValueError):
        probe_module.probe(durations)


def test_probe_fails_if_frontend_contract_is_unknown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(probe_module, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "web/src/lib/audio/clip-file.ts"
    source.parent.mkdir(parents=True)
    source.write_text("export function encode() {}", encoding="utf-8")
    with pytest.raises(ValueError, match="encoding contract changed"):
        probe_module.probe([30])
