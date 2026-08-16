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
    MIDI_CC64,
    SustainEvidence,
    SustainEvidenceConfig,
    extract_sustain_evidence,
)
from app.pipeline.transcribe import NoteEvent
from app.pipeline.voice_compression import compress_notation_durations
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
        NoteEvent(index * 0.25, index * 0.25 + 0.5, 60 + index, 80, 0.8)
        for index in range(8)
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


def test_fixed_arpeggio_uses_audio_evidence_without_changing_note_events() -> None:
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

    assert events == original_events
    assert timeline["cleanup"]["reason_counts"]["HARMONIC_CANDIDATE_REMOVED"] > 0
    assert compression["applied"] is True
    assert compression["compressed_group_count"] > 0
    assert compression["pedal_marking_applied"] is False
    assert structure["voice_count"] < 100
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
