import json
from pathlib import Path

import pretty_midi
from music21 import converter, expressions

from app.pipeline.analysis import StructureAnalysis
from app.pipeline.harmony import NotationGroup
from app.pipeline.score import build_score, write_musicxml
from app.pipeline.score_validation import score_structure_summary
from app.pipeline.sustain import (
    AUDIO_ONSET_RESONANCE,
    AUDIO_SUSTAIN_PEDAL,
    MIDI_CC64,
    SustainEvidence,
    SustainEvidenceConfig,
    extract_sustain_evidence,
    infer_audio_pedal_intervals,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voice_compression import (
    SAME_PITCH_RESONANCE_MERGED,
    compress_notation_durations,
)
from app.pipeline.voicing import assign_voices

FIXTURE_ROOT = Path(__file__).parent / "fixtures/audio"


def _evidence(onsets: tuple[float, ...]) -> SustainEvidence:
    return SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(AUDIO_ONSET_RESONANCE,),
        independent_onset_seconds=onsets,
        resonant_intervals=tuple(zip(onsets, onsets[1:], strict=False)),
        cc64_intervals=(),
    )


def _group(start: int, end: int, *pitches: int) -> NotationGroup:
    return NotationGroup(start, end, pitches, 80, 0.8)


def test_dense_resonant_arpeggio_compresses_to_one_notation_voice() -> None:
    groups = [_group(start, start + 4, 48 + index) for index, start in enumerate(range(0, 16, 2))]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    assert result.applied is True
    assert result.compressed_group_count == 7
    assert len(assign_voices(result.groups)) == 1
    assert [group.end_units for group in result.groups[:-1]] == list(range(2, 16, 2))
    assert result.summary()["pedal_marking_applied"] is False


def test_dense_same_pitch_retriggers_remain_distinct_onsets_in_one_voice() -> None:
    groups = [_group(start, start + 4, 60) for start in range(0, 16, 2)]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    assert result.applied is True
    assert len(result.groups) == 8
    assert len(assign_voices(result.groups)) == 1
    assert [group.start_units for group in result.groups] == list(range(0, 16, 2))


def test_overlapping_same_pitch_without_retrigger_evidence_is_merged() -> None:
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(AUDIO_ONSET_RESONANCE,),
        independent_onset_seconds=(0.0,),
        resonant_intervals=((0.0, 0.5),),
        cc64_intervals=(),
    )
    groups = [_group(0, 16, 60), _group(4, 12, 60)]

    result = compress_notation_durations(groups, 0.5, 0, evidence)

    assert [(group.start_units, group.end_units) for group in result.groups] == [(0, 16)]
    assert result.coalesced_group_count == 1
    assert result.reason_codes == (SAME_PITCH_RESONANCE_MERGED,)


def test_overlapping_same_pitch_with_retrigger_evidence_stays_distinct() -> None:
    groups = [_group(0, 16, 60), _group(4, 12, 60)]

    result = compress_notation_durations(groups, 0.5, 0, _evidence((0.0, 0.5)))

    assert result.groups == groups
    assert len(assign_voices(result.groups)) == 2


def test_overlapping_chord_pitch_without_retrigger_evidence_is_merged() -> None:
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(AUDIO_ONSET_RESONANCE,),
        independent_onset_seconds=(0.0,),
        resonant_intervals=((0.0, 0.5),),
        cc64_intervals=(),
    )
    groups = [_group(0, 16, 52, 60), _group(4, 12, 60)]

    result = compress_notation_durations(groups, 0.5, 0, evidence)

    assert result.groups == [_group(0, 16, 52, 60)]
    assert result.coalesced_group_count == 1
    assert result.reason_codes == (SAME_PITCH_RESONANCE_MERGED,)


def test_overlapping_chords_merge_shared_pitch_without_retrigger_evidence() -> None:
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(AUDIO_ONSET_RESONANCE,),
        independent_onset_seconds=(0.0,),
        resonant_intervals=((0.0, 0.5),),
        cc64_intervals=(),
    )
    groups = [_group(0, 16, 52, 60), _group(4, 12, 60, 67)]

    result = compress_notation_durations(groups, 0.5, 0, evidence)

    assert result.groups == [_group(0, 16, 52, 60), _group(4, 12, 67)]
    assert result.coalesced_group_count == 1
    assert result.reason_codes == (SAME_PITCH_RESONANCE_MERGED,)


def test_sparse_sustained_chords_keep_their_full_durations() -> None:
    groups = [
        _group(0, 12, 48, 55, 60, 64),
        _group(8, 20, 50, 57, 62, 65),
        _group(16, 28, 43, 55, 59, 62),
    ]
    before = [(group.start_units, group.end_units, group.pitches) for group in groups]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence((0.0, 1.0, 2.0)),
    )

    assert result.applied is False
    assert [
        (group.start_units, group.end_units, group.pitches) for group in result.groups
    ] == before


def test_missing_audio_or_cc64_evidence_never_compresses_overlap() -> None:
    groups = [_group(start, start + 4, 60 + index) for index, start in enumerate(range(0, 16, 2))]

    result = compress_notation_durations(groups, 0.5, 0, None)

    assert result.applied is False
    assert result.groups == groups
    assert result.reason_codes == ("SUSTAIN_EVIDENCE_UNAVAILABLE",)


def test_sustained_bass_across_dense_melody_is_preserved_as_independent_voice() -> None:
    groups = [
        _group(0, 16, 36),
        *[_group(start, start + 4, 60 + index) for index, start in enumerate(range(0, 16, 2))],
    ]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    bass = next(group for group in result.groups if group.pitches == (36,))
    assert (bass.start_units, bass.end_units) == (0, 16)
    assert len(assign_voices(result.groups)) == 2


def test_simple_arpeggio_keeps_evidenced_sustained_bass_end_to_end() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [NoteEvent(0.0, 6.0, 36, 90, 0.9)]
    events.extend(
        NoteEvent(index * 0.25, index * 0.25 + 0.5, pitch, 80, 0.8)
        for index, pitch in enumerate(pitches * 3)
    )
    onsets = tuple(index * 0.25 for index in range(24))

    scored = build_score(events, sustain_evidence=_evidence(onsets))

    bass_duration = sum(
        float(item.duration.quarterLength)
        for item in scored.score.recurse().notes
        if item.isNote and item.pitch.midi == 36
    )
    compression = scored.reconstruction["voice_compression"]
    assert scored.reconstruction["voicing"]["strategy"] == "simple_arpeggio_stable_zone"
    assert compression["single_voice_applied"] is False
    assert compression["notation_voice_count"] == 2
    assert bass_duration == 12.0


def test_simple_arpeggio_keeps_sustained_pattern_pitch_end_to_end() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.2, pitch, 90, 0.9)
        for index, pitch in enumerate(pitches * 3)
    ]
    events.append(NoteEvent(0.25, 2.0, 48, 88, 0.85))
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(MIDI_CC64,),
        independent_onset_seconds=tuple(index * 0.25 for index in range(24)),
        resonant_intervals=(),
        cc64_intervals=((0.0, 6.0),),
    )

    scored = build_score(events, sustain_evidence=evidence)
    c3_notes = [
        (float(item.getOffsetInHierarchy(scored.score)), float(item.duration.quarterLength))
        for item in scored.score.recurse().notes
        if item.isNote and item.pitch.midi == 48
    ]

    assert (0.5, 3.5) in c3_notes
    assert scored.reconstruction["voice_compression"]["single_voice_applied"] is False


def test_distant_pedal_does_not_authorize_arpeggio_filtering() -> None:
    pitches = (48, 55, 60, 64, 67, 72, 67, 64)
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.2, pitch, 90, 0.9)
        for index, pitch in enumerate(pitches * 3)
    ]
    events.append(NoteEvent(0.25, 0.45, 48, 88, 0.85))
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(MIDI_CC64,),
        independent_onset_seconds=(100.0,),
        resonant_intervals=(),
        cc64_intervals=((100.0, 101.0),),
    )

    scored = build_score(events, sustain_evidence=evidence)

    assert len(scored.notation_notes) == 25
    assert scored.reconstruction["arpeggio_filter"]["removed_event_count"] == 0
    assert list(scored.score.recurse().getElementsByClass(expressions.PedalMark)) == []


def test_preassigned_non_target_arpeggio_does_not_force_single_voice() -> None:
    pitches = (53, 57, 59, 60, 65, 69, 74, 69)
    events = [NoteEvent(0.125, 6.0, 48, 90, 0.9, hand="left")]
    events.extend(
        NoteEvent(
            index * 0.25,
            index * 0.25 + 0.5,
            pitch,
            80,
            0.8,
            hand="left" if pitch <= 60 else "right",
        )
        for index, pitch in enumerate(pitches * 3)
    )
    onsets = tuple(index * 0.25 for index in range(24))

    scored = build_score(events, sustain_evidence=_evidence(onsets))

    bass_duration = sum(
        float(item.duration.quarterLength)
        for item in scored.score.recurse().notes
        if item.isNote and item.pitch.midi == 48
    )
    compression = scored.reconstruction["voice_compression"]
    assert scored.reconstruction["voicing"]["strategy"] == "continuity"
    assert compression["single_voice_applied"] is False
    assert compression["notation_voice_count"] > 1
    assert bass_duration == 11.75


def test_sustained_inner_voice_entering_after_run_start_is_not_compressed() -> None:
    groups = [
        *[_group(start, start + 4, 60 + index) for index, start in enumerate(range(0, 16, 2))],
        _group(2, 16, 52),
    ]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    inner_voice = next(group for group in result.groups if group.pitches == (52,))
    assert (inner_voice.start_units, inner_voice.end_units) == (2, 16)
    assert len(assign_voices(result.groups)) == 2


def test_partial_chord_retrigger_does_not_cut_independent_sustained_pitch() -> None:
    groups = [
        _group(0, 4, 72),
        _group(2, 16, 52, 60),
        _group(4, 8, 60),
        *[_group(start, start + 4, 72 + index) for index, start in enumerate(range(6, 16, 2))],
    ]

    result = compress_notation_durations(
        groups,
        seconds_per_quarter=0.5,
        measure_offset_units=0,
        evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    sustained = next(
        group for group in result.groups if group.start_units == 2 and group.pitches == (52,)
    )
    retriggered = next(
        group for group in result.groups if group.start_units == 2 and group.pitches == (60,)
    )
    assert sustained.end_units == 16
    assert retriggered.end_units == 4


def test_cc64_evidence_survives_unavailable_audio(tmp_path: Path) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    piano.notes = [pretty_midi.Note(80, 60, 0.0, 0.5)]
    piano.control_changes = [
        pretty_midi.ControlChange(64, 127, 0.0),
        pretty_midi.ControlChange(64, 0, 1.0),
    ]
    midi.instruments.append(piano)

    evidence = extract_sustain_evidence(tmp_path / "missing.wav", midi)

    assert evidence.status == "available"
    assert evidence.sources == (MIDI_CC64,)
    assert evidence.cc64_intervals == ((0.0, 1.0),)


def test_unreleased_cc64_closes_at_midi_end_and_overlaps_are_merged(tmp_path: Path) -> None:
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    for start in (0.0, 0.25):
        piano = pretty_midi.Instrument(program=0)
        piano.notes = [pretty_midi.Note(80, 60, start, 1.5)]
        piano.control_changes = [pretty_midi.ControlChange(64, 127, start)]
        midi.instruments.append(piano)

    evidence = extract_sustain_evidence(tmp_path / "missing.wav", midi)

    assert evidence.status == "available"
    assert evidence.sources == (MIDI_CC64,)
    assert evidence.cc64_intervals == ((0.0, 1.5),)


def test_explicit_cc64_writes_pedal_mark_but_audio_resonance_alone_does_not(
    tmp_path: Path,
) -> None:
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.5, 60 + index, 80, 0.8) for index in range(8)
    ]
    cc64_evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(MIDI_CC64,),
        independent_onset_seconds=tuple(index * 0.25 for index in range(8)),
        resonant_intervals=(),
        cc64_intervals=((0.0, 1.5),),
    )

    with_cc64 = build_score(events, sustain_evidence=cc64_evidence)
    audio_only = build_score(
        events,
        sustain_evidence=_evidence(tuple(index * 0.25 for index in range(8))),
    )

    assert len(list(with_cc64.score.recurse().getElementsByClass(expressions.PedalMark))) == 1
    assert with_cc64.reconstruction["voice_compression"]["pedal_marking_applied"] is True
    assert with_cc64.reconstruction["voice_compression"]["pedal_marking_count"] == 1
    assert list(audio_only.score.recurse().getElementsByClass(expressions.PedalMark)) == []
    assert audio_only.reconstruction["voice_compression"]["pedal_marking_applied"] is False

    cc64_path = tmp_path / "cc64.musicxml"
    audio_only_path = tmp_path / "audio-only.musicxml"
    write_musicxml(with_cc64, cc64_path)
    write_musicxml(audio_only, audio_only_path)
    parsed_cc64 = converter.parse(str(cc64_path))
    parsed_audio_only = converter.parse(str(audio_only_path))

    assert len(list(parsed_cc64[expressions.PedalMark])) == 1
    assert list(parsed_audio_only[expressions.PedalMark]) == []
    assert cc64_path.read_text(encoding="utf-8").count("<pedal ") == 2
    assert "<pedal " not in audio_only_path.read_text(encoding="utf-8")


def test_multistaff_pedal_anchors_stay_on_one_staff(tmp_path: Path) -> None:
    events = [
        NoteEvent(0.0, 0.4, 48, 80, 0.8),
        NoteEvent(0.5, 0.9, 72, 80, 0.8),
        NoteEvent(1.5, 1.9, 76, 80, 0.8),
    ]
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(MIDI_CC64,),
        independent_onset_seconds=(0.0, 0.5, 1.5),
        resonant_intervals=(),
        cc64_intervals=((0.0, 1.5),),
    )

    scored = build_score(events, sustain_evidence=evidence)
    destination = tmp_path / "same-staff-pedal.musicxml"
    write_musicxml(scored, destination)
    parsed = converter.parse(str(destination))
    xml = destination.read_text(encoding="utf-8")

    assert len(list(parsed[expressions.PedalMark])) == 1
    assert xml.count('<pedal line="yes" number="1" type="start"') == 1
    assert xml.count('<pedal line="yes" number="1" type="stop"') == 1


def test_sparse_audio_resonance_does_not_create_a_pedal_mark() -> None:
    onsets = tuple(float(index) for index in range(12))
    events = [
        NoteEvent(onset, onset + 1.5, 60 + index % 4, 80, 0.8) for index, onset in enumerate(onsets)
    ]

    scored = build_score(events, sustain_evidence=_evidence(onsets))

    assert list(scored.score.recurse().getElementsByClass(expressions.PedalMark)) == []
    assert scored.reconstruction["voice_compression"]["pedal_marking_applied"] is False


def test_continuous_audio_pedal_evidence_creates_a_mark_for_non_arpeggio() -> None:
    intervals = tuple((index * 0.25, (index + 1) * 0.25) for index in range(9))
    audio_pedal = infer_audio_pedal_intervals(intervals)
    evidence = SustainEvidence(
        version=SustainEvidenceConfig().version,
        status="available",
        sources=(AUDIO_ONSET_RESONANCE, AUDIO_SUSTAIN_PEDAL),
        independent_onset_seconds=tuple(index * 0.25 for index in range(10)),
        resonant_intervals=intervals,
        cc64_intervals=(),
        audio_pedal_intervals=audio_pedal,
    )
    events = [
        NoteEvent(index * 0.25, index * 0.25 + 0.5, 60 + index % 3, 80, 0.8) for index in range(10)
    ]

    scored = build_score(events, sustain_evidence=evidence)

    assert audio_pedal == ((0.0, 2.25),)
    assert scored.reconstruction["voicing"]["strategy"] == "continuity"
    assert len(list(scored.score.recurse().getElementsByClass(expressions.PedalMark))) == 1


def test_audio_pedal_detection_starts_at_eight_dense_onsets() -> None:
    seven_intervals = tuple((index * 0.25, (index + 1) * 0.25) for index in range(7))
    six_intervals = seven_intervals[:-1]

    assert infer_audio_pedal_intervals(seven_intervals) == ((0.0, 1.75),)
    assert infer_audio_pedal_intervals(six_intervals) == ()


def test_fixed_arpeggio_filters_resonance_before_voice_compression() -> None:
    timeline_path = FIXTURE_ROOT / "structure-review-artifacts/04-arpeggios/timeline.json"
    timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
    events = [
        NoteEvent(**{key: value for key, value in item.items() if key != "id"})
        for item in timeline["notes"]
    ]
    original_events = list(events)
    evidence = extract_sustain_evidence(
        FIXTURE_ROOT / "generated/04-arpeggios.wav",
        pretty_midi.PrettyMIDI(str(FIXTURE_ROOT / "generated/04-arpeggios.mid")),
    )

    scored = build_score(
        events,
        analysis=StructureAnalysis(**timeline["analysis"]),
        sustain_evidence=evidence,
    )
    structure = score_structure_summary(scored.score, validate_measure_durations=True)
    compression = scored.reconstruction["voice_compression"]
    arpeggio_filter = scored.reconstruction["arpeggio_filter"]

    assert events == original_events
    assert timeline["cleanup"]["reason_counts"]["HARMONIC_CANDIDATE_REMOVED"] > 0
    assert arpeggio_filter["applied"] is True
    assert arpeggio_filter["removed_event_count"] == 97
    assert arpeggio_filter["matched_slot_count"] == 119
    assert compression["applied"] is False
    assert compression["compressed_group_count"] == 0
    assert compression["pedal_marking_applied"] is True
    assert compression["pedal_marking_count"] == 1
    assert len(list(scored.score.recurse().notes)) == 119
    assert structure["voice_count"] == 0
    assert structure["rest_count"] < 150
    assert structure["short_rest_count"] == 0
    assert structure["errors"] == []


def test_fixed_sustain_chords_are_not_flattened_into_a_dense_melody() -> None:
    timeline = json.loads(
        (FIXTURE_ROOT / "structure-review-artifacts/06-sustain/timeline.json").read_text(
            encoding="utf-8"
        )
    )
    events = [
        NoteEvent(**{key: value for key, value in item.items() if key != "id"})
        for item in timeline["notes"]
    ]
    evidence = extract_sustain_evidence(
        FIXTURE_ROOT / "generated/06-sustain.wav",
        pretty_midi.PrettyMIDI(str(FIXTURE_ROOT / "generated/06-sustain.mid")),
    )

    scored = build_score(
        events,
        analysis=StructureAnalysis(**timeline["analysis"]),
        sustain_evidence=evidence,
    )

    assert scored.reconstruction["voice_compression"]["applied"] is False
    assert scored.reconstruction["chord_count"] >= 10
    assert scored.reconstruction["voice_compression"]["pedal_marking_applied"] is False
