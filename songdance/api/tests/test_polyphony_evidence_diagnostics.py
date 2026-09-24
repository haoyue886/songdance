from dataclasses import asdict

import pytest

from app.pipeline.crossing_tail_cleanup import _is_uninterrupted_decay
from app.pipeline.harmonics import NoteOnsetEvidence
from scripts.polyphony_evidence_diagnostics import evidence_limits


def observation(**updates):
    values = dict(
        pitch=60,
        start_sec=1,
        end_sec=2,
        onset_growth=0.6,
        independent_onset=False,
        pre_onset_energy=1,
        onset_energy=0.6,
        decay_fit_error=0.05,
        transient_fit_error=0.01,
    )
    values.update(updates)
    return NoteOnsetEvidence(**values)


@pytest.mark.parametrize("start,clamped", [(0, True), (0.01136, True), (0.08, False), (1, False)])
def test_probe_boundary_does_not_imply_absent_attack(start, clamped):
    result = evidence_limits({"start_sec": start}, [asdict(observation())])
    assert result["pre_onset_probe_clamped"] is clamped
    assert result["local_decay_checks_failed"] == []
    assert "not the full" in result["scope"]


@pytest.mark.parametrize(
    "changes",
    [
        {},
        {"independent_onset": True},
        {"onset_growth": 1.01},
        {"onset_growth": None},
        {"pre_onset_energy": 0},
        {"onset_energy": 2},
        {"decay_fit_error": None},
        {"decay_fit_error": 0.05001},
        {"decay_fit_error": float("nan")},
        {"transient_fit_error": float("inf")},
        {"transient_fit_error": 0.01001},
        {"transient_fit_error": -1},
    ],
)
def test_diagnostics_agree_with_existing_local_predicate(changes):
    o = observation(**changes)
    failures = evidence_limits({"start_sec": 1}, [asdict(o)])["local_decay_checks_failed"]
    assert (not failures) == _is_uninterrupted_decay(o)


@pytest.mark.parametrize("observations", [[], [asdict(observation())] * 2])
def test_missing_and_ambiguous_measurements_are_explicit(observations):
    assert evidence_limits({"start_sec": 1}, observations)["local_decay_checks_failed"] == [
        "missing_or_ambiguous_observation"
    ]
