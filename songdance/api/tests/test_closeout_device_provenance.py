import json

from scripts.compare_piano_model_outputs import note_metrics, read_midi
from scripts.piano_comparison_cases import ROOT, file_sha256


def test_model_specific_quality_findings_recompute_without_mixing_candidates():
    fixtures = ROOT / "tests/fixtures/audio"
    report = json.loads(
        (
            fixtures / "candidates/closeout-review-20260919-v1/10-model-provenance-audit.json"
        ).read_text()
    )
    reference = read_midi(fixtures / "generated/10-device.mid")
    assert report["reference_sha256"] == file_sha256(fixtures / "generated/10-device.mid")
    for row in report["models"].values():
        path = ROOT / row["path"]
        assert file_sha256(path) == row["sha256"]
        estimated = read_midi(path)
        for group, predicate in [
            ("bass", lambda n: n["pitch"] < 60),
            ("treble", lambda n: n["pitch"] >= 60),
        ]:
            assert row["metrics"][group] == {
                str(t): note_metrics(
                    [n for n in reference if predicate(n)],
                    [n for n in estimated if predicate(n)],
                    t,
                )
                for t in (0.05, 0.1)
            }
    basic = report["models"]["basic_raw"]["metrics"]["bass"]["0.1"]
    candidate = report["models"]["transkun_reviewed_candidate"]["metrics"]["bass"]["0.1"]
    assert [(n["pitch"], n["start_sec"]) for n in basic["missing_reference_notes"]] == [(36, 12.0)]
    assert [(n["pitch"], n["start_sec"]) for n in candidate["missing_reference_notes"]] == [
        (36, 0.0),
        (36, 15.0),
        (36, 16.0),
    ]
    assert report["production_eligible"] is False
