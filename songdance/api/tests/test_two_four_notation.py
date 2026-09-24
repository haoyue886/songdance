from dataclasses import replace

import numpy as np
import pytest

from app.pipeline.analysis import AnalysisConfig, _downbeats, fallback_analysis
from app.pipeline.quantize import _measure_units
from app.pipeline.score import NotationContext, build_score, write_musicxml, write_quantized_midi
from app.pipeline.score_io import read_musicxml_structure
from app.pipeline.transcribe import NoteEvent
from scripts.compare_piano_model_outputs import read_midi


@pytest.mark.parametrize("meter,beats", [("2/4", 2), ("3/4", 3), ("4/4", 4), ("6/8", 3)])
def test_meter_units_and_downbeat_grouping_agree(meter, beats):
    analysis = replace(fallback_analysis(AnalysisConfig(), "test"), time_signature=meter)
    assert _measure_units(analysis, 4) == beats * 4
    assert _downbeats(np.arange(12, dtype=float), meter, 0) == tuple(
        float(x) for x in range(0, 12, beats)
    )


def test_explicit_two_four_builds_and_exports_without_keyerror(tmp_path):
    events = [NoteEvent(i * 0.5, i * 0.5 + 0.4, 60 + i % 4, 80, 0.8) for i in range(8)]
    context = NotationContext(
        time_signature="2/4",
        time_signature_source="test",
        tempo_bpm=60,
        tempo_source="test",
        measure_offset_units=0,
        measure_offset_source="test",
    )
    result = build_score(events, notation_context=context)
    xml = tmp_path / "score.musicxml"
    midi = tmp_path / "score.mid"
    write_musicxml(result, xml)
    write_quantized_midi(result, midi)
    summary = read_musicxml_structure(xml)
    assert summary["time_signatures"] == ["2/4"]
    assert summary["measure_duration_error_count"] == 0
    assert len(read_midi(midi)) == 8
