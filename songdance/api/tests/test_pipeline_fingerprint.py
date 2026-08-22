from pathlib import Path

from scripts.human_quality_gate import PIPELINE_FILES, compute_suite_fingerprint
from scripts.structure_quality_gate import compute_structure_suite_fingerprint


def test_fixed_suite_fingerprints_cover_arpeggio_audio_evidence(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent / "fixtures/audio"
    pipeline_root = tmp_path / "pipeline"
    pipeline_root.mkdir()
    for filename in PIPELINE_FILES:
        (pipeline_root / filename).write_text(filename, encoding="utf-8")

    human_before = compute_suite_fingerprint(fixture_root, pipeline_root)
    structure_before = compute_structure_suite_fingerprint(fixture_root, pipeline_root)
    evidence_module = pipeline_root / "arpeggio_audio_evidence.py"
    evidence_module.write_text("changed", encoding="utf-8")

    assert "arpeggio_audio_evidence.py" in PIPELINE_FILES
    assert compute_suite_fingerprint(fixture_root, pipeline_root) != human_before
    assert compute_structure_suite_fingerprint(fixture_root, pipeline_root) != structure_before
