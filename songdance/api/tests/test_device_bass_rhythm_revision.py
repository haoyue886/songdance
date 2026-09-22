from xml.etree import ElementTree as ET

import pytest

from scripts.piano_comparison_cases import ROOT
from scripts.revise_device_bass_notation import revise, timed_notes, treble_nodes


def test_actual_reviewed_score_preserves_all_onsets_and_treble(tmp_path):
    source = ROOT.parents[1] / "teacher-transkun-candidates-2026-09-16/10-device/candidate.musicxml"
    out = tmp_path / "score.musicxml"
    changes = revise(source, out)
    assert len(changes) == 26
    assert timed_notes(source) == timed_notes(out)
    assert len(timed_notes(out)) == 87
    assert treble_nodes(source) == treble_nodes(out)
    assert len(ET.parse(out).findall(".//note/rest")) == 4
    with pytest.raises(ValueError, match="exists"):
        revise(source, out)


def test_other_voice_rest_does_not_extend_bass(tmp_path):
    source = tmp_path / "source.xml"
    source.write_text("""<score-partwise><part><measure number="1">
    <note><pitch><step>C</step><octave>2</octave></pitch><duration>17640</duration>
    <voice>2</voice><type>quarter</type><dot/><dot/><staff>2</staff></note>
    <note><rest/><duration>2520</duration><voice>3</voice><staff>2</staff></note>
    </measure></part></score-partwise>""")
    out = tmp_path / "out.xml"
    assert revise(source, out) == []
    assert ET.parse(out).findtext(".//note/duration") == "17640"
