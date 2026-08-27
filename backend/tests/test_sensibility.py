from __future__ import annotations

from app.model.playbook_schema import AllocationRule, PlaybookProposal
from app.model.sensibility import is_sensible, to_sensible_candidate

BUDGET = 6


def _proposal(**overrides):
    defaults = dict(
        rules=[
            AllocationRule(decline_class="soft", priority_weight=1.5, rationale="soft declines retry with moderate priority"),
            AllocationRule(decline_class="technical", priority_weight=1.0, rationale="technical declines are a network retry candidate"),
        ],
        scarcity_remaining_budget_threshold=1,
        defer_priority_cutoff=1.2,
    )
    defaults.update(overrides)
    return PlaybookProposal(**defaults)


def test_a_well_formed_proposal_is_sensible():
    ok, reason = is_sensible(_proposal(), BUDGET)
    assert ok, reason


def test_missing_a_class_is_not_sensible():
    ok, reason = is_sensible(_proposal(rules=[
        AllocationRule(decline_class="soft", priority_weight=1.5, rationale="soft retry priority"),
    ]), BUDGET)
    assert not ok
    assert "technical" in reason


def test_duplicate_class_is_not_sensible():
    ok, reason = is_sensible(_proposal(rules=[
        AllocationRule(decline_class="soft", priority_weight=1.5, rationale="soft retry priority"),
        AllocationRule(decline_class="soft", priority_weight=2.0, rationale="soft retry priority again"),
        AllocationRule(decline_class="technical", priority_weight=1.0, rationale="technical retry candidate"),
    ]), BUDGET)
    assert not ok
    assert "soft" in reason


def test_absurdly_large_weight_is_not_sensible():
    ok, reason = is_sensible(_proposal(rules=[
        AllocationRule(decline_class="soft", priority_weight=999999.0, rationale="soft retry priority"),
        AllocationRule(decline_class="technical", priority_weight=1.0, rationale="technical retry candidate"),
    ]), BUDGET)
    assert not ok
    assert "priority_weight" in reason


def test_off_topic_rationale_is_not_sensible():
    ok, reason = is_sensible(_proposal(rules=[
        AllocationRule(decline_class="soft", priority_weight=1.5, rationale="the sky is blue and birds fly south for winter"),
        AllocationRule(decline_class="technical", priority_weight=1.0, rationale="technical retry candidate"),
    ]), BUDGET)
    assert not ok
    assert "rationale" in reason


def test_threshold_above_the_real_card_budget_is_not_sensible():
    ok, reason = is_sensible(_proposal(scarcity_remaining_budget_threshold=BUDGET + 1), BUDGET)
    assert not ok
    assert "scarcity_remaining_budget_threshold" in reason


def test_negative_or_absurd_cutoff_is_not_sensible():
    ok, reason = is_sensible(_proposal(defer_priority_cutoff=1_000_000.0), BUDGET)
    assert not ok
    assert "defer_priority_cutoff" in reason


def test_to_sensible_candidate_extracts_the_weight_ratio_correctly():
    candidate = to_sensible_candidate(_proposal())
    assert candidate.weight_ratio == 1.5 / 1.0
    assert candidate.defer_priority_cutoff == 1.2
    assert candidate.scarcity_remaining_budget_threshold == 1
