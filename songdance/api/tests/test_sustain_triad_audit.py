from scripts.audit_sustain_triad_candidate import audit


def test_confirmed_triad_candidate_accounts_for_every_raw_event():
    result = audit()
    assert result["contract_status"] == "confirmed_by_expert_review"
    assert result["truth_note_count"] == result["matched_truth_count"] == 45
    assert result["raw_note_count"] == result["accounted_event_count"] == 79
    assert result["extra_event_count"] == 34
    assert sum(result["classification_counts"].values()) == 34
    assert result["classification_counts"]["unclassified"] == 0
    assert all(
        item["classification_is_deletion_evidence"] is False for item in result["extra_events"]
    )
    assert len(result["matched_events"]) == 45
    assert all(item["candidate_count"] == 1 for item in result["matched_events"])
    assert max(abs(item["onset_error_seconds"]) for item in result["matched_events"]) < 0.012
    for strategy in result["strategy_comparison"]:
        decisions = [
            item["strategy_decisions"][strategy]["decision"] for item in result["extra_events"]
        ]
        assert (
            decisions.count("removed")
            == result["strategy_comparison"][strategy]["removed_event_count"]
        )
        assert all(
            item["strategy_decisions"][strategy]["decision"] == "retained"
            for item in result["matched_events"]
        )


def test_candidate_bass_priority_does_not_claim_an_unobserved_improvement():
    result = audit()
    baseline = result["strategy_comparison"]["default"]
    candidate = result["strategy_comparison"]["candidate_bass_priority"]
    assert baseline["recall"] == candidate["recall"] == 1.0
    assert candidate["f1"] == baseline["f1"]
    assert candidate["removed_event_count"] == baseline["removed_event_count"]
    assert candidate["production_eligible"] is False
    assert candidate["blocking_reasons"] == ["NO_IMPROVEMENT_OVER_DEFAULT"]
    assert result["production_change"] is False


def test_velocity_scan_is_reported_as_candidate_only():
    result = audit()
    baseline = result["strategy_comparison"]["default"]
    candidate = result["strategy_comparison"]["candidate_velocity_0_60"]
    assert candidate["recall"] == baseline["recall"] == 1.0
    assert candidate["f1"] > baseline["f1"]
    assert candidate["removed_event_count"] == 18
    assert candidate["production_eligible"] is False
    assert candidate["blocking_reasons"] == ["REAL_BASS_OCTAVE_FALSE_REMOVAL"]
    assert result["production_change"] is False
