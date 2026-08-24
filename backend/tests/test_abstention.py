from __future__ import annotations

from app.model.abstention import (
    MAX_CUTOFF_CV,
    MAX_WEIGHT_RATIO_CV,
    MIN_MODAL_AGREEMENT,
    MIN_SENSIBLE_COUNT,
    SensibleCandidate,
    decide_abstention,
)


def _stable_candidates(n: int) -> list[SensibleCandidate]:
    """Identical numbers every time -- zero dispersion, unanimous modal agreement --
    the clean 'should not abstain' baseline every single-rule test perturbs from."""
    return [SensibleCandidate(weight_ratio=1.5, defer_priority_cutoff=1.2, scarcity_remaining_budget_threshold=1) for _ in range(n)]


def test_stable_generations_do_not_abstain():
    verdict = decide_abstention(total_generations=20, sensible=_stable_candidates(20))
    assert verdict.abstained is False
    assert verdict.reason is None


def test_rule_a_fires_below_the_sensible_count_floor():
    sensible = _stable_candidates(MIN_SENSIBLE_COUNT - 1)
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is True
    assert "Rule A" in verdict.reason


def test_rule_a_does_not_fire_exactly_at_the_floor():
    sensible = _stable_candidates(MIN_SENSIBLE_COUNT)
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is False


def test_rule_b_fires_on_high_weight_ratio_dispersion():
    sensible = [
        SensibleCandidate(weight_ratio=r, defer_priority_cutoff=1.2, scarcity_remaining_budget_threshold=1)
        for r in [0.1, 5.0, 0.2, 4.5, 0.15, 3.8, 0.3, 4.1, 0.25, 3.5, 0.4, 4.9, 0.5, 3.2, 0.6, 4.4, 0.7]
    ]
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is True
    assert "weight_ratio CV" in verdict.reason


def test_rule_b_fires_on_high_cutoff_dispersion_independent_of_ratio():
    """A provider stable on the ratio but scattered on defer_priority_cutoff must not
    pass silently -- the two continuous parameters are checked independently."""
    sensible = [
        SensibleCandidate(weight_ratio=1.5, defer_priority_cutoff=c, scarcity_remaining_budget_threshold=1)
        for c in [0.1, 5.0, 0.2, 4.5, 0.15, 3.8, 0.3, 4.1, 0.25, 3.5, 0.4, 4.9, 0.5, 3.2, 0.6, 4.4, 0.7]
    ]
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is True
    assert "defer_priority_cutoff CV" in verdict.reason


def test_rule_c_fires_on_low_modal_agreement_for_the_discrete_threshold():
    sensible = [
        SensibleCandidate(weight_ratio=1.5, defer_priority_cutoff=1.2, scarcity_remaining_budget_threshold=t)
        for t in [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1]
    ]
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is True
    assert "Rule C" in verdict.reason


def test_rule_c_does_not_fire_right_at_the_modal_agreement_floor():
    # 60% of 20 sensible generations share the modal value.
    sensible = (
        [SensibleCandidate(1.5, 1.2, 1) for _ in range(12)]
        + [SensibleCandidate(1.5, 1.2, 2) for _ in range(8)]
    )
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert verdict.abstained is False


def test_rules_are_checked_in_order_a_then_b_then_c():
    """A generation set failing multiple rules reports the first one checked, per the
    pre-registered order in the module docstring."""
    sensible = [
        SensibleCandidate(weight_ratio=r, defer_priority_cutoff=1.2, scarcity_remaining_budget_threshold=1)
        for r in [0.1, 5.0]
    ]  # fails Rule A (too few) AND would fail Rule B's dispersion check if reached
    verdict = decide_abstention(total_generations=20, sensible=sensible)
    assert "Rule A" in verdict.reason
