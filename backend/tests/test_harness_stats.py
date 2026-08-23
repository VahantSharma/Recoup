from datetime import datetime, timezone

import pytest

from app.corpus_builder import build_corpus
from app.harness.policies import ControlPolicy, RulesOnlyPolicy
from app.harness.run import CaseArmResult, run_ablation
from app.harness.stats import paired_bootstrap_lift


def _row(case_id, arm, amount, recovered):
    return CaseArmResult(
        case_id=case_id, arm=arm, amount_paise=amount, decline_class="soft",
        recovered=recovered, recovered_via="action" if recovered else None,
        resolved_at=None, attempt_count=1, violation_count=0,
        final_status="recovered" if recovered else "not_recovered",
    )


def test_hand_computed_point_estimates_exact_no_variance_case():
    """A always recovers, B never does -- every case's amount is 1000 paise.
    Point rate lift must be exactly 1.0, amount lift exactly 5000 (5 cases * 1000),
    and with zero variance in the paired differences, the bootstrap CI collapses to a
    single point."""
    a = [_row(f"c{i}", "a", 1000, True) for i in range(5)]
    b = [_row(f"c{i}", "b", 1000, False) for i in range(5)]

    result = paired_bootstrap_lift(a, b, n_bootstrap=500, seed=1)

    assert result.rate_a == 1.0
    assert result.rate_b == 0.0
    assert result.rate_lift == 1.0
    assert result.rate_lift_ci_low == pytest.approx(1.0)
    assert result.rate_lift_ci_high == pytest.approx(1.0)
    assert result.amount_lift_paise == 5000
    assert result.amount_lift_ci_low_paise == pytest.approx(5000)
    assert result.amount_lift_ci_high_paise == pytest.approx(5000)


def test_hand_computed_mixed_case():
    """3 cases: case0 -- A recovers (1000), B doesn't. case1 -- neither recovers.
    case2 -- both recover the same amount (net 0 for that case). Paired point
    estimates computed by hand: rate_lift = (1-0 + 0-0 + 1-1)/3 = 1/3.
    amount_lift = (1000-0) + (0-0) + (500-500) = 1000."""
    a = [_row("c0", "a", 1000, True), _row("c1", "a", 500, False), _row("c2", "a", 500, True)]
    b = [_row("c0", "b", 1000, False), _row("c1", "b", 500, False), _row("c2", "b", 500, True)]

    result = paired_bootstrap_lift(a, b, n_bootstrap=1000, seed=2)

    assert result.rate_lift == pytest.approx(1 / 3)
    assert result.amount_lift_paise == 1000


def test_ci_bounds_are_ordered_and_contain_the_point_estimate_when_variance_exists():
    a = [_row(f"c{i}", "a", 1000, i % 3 == 0) for i in range(60)]
    b = [_row(f"c{i}", "b", 1000, i % 5 == 0) for i in range(60)]

    result = paired_bootstrap_lift(a, b, n_bootstrap=1000, seed=3)

    assert result.rate_lift_ci_low <= result.rate_lift <= result.rate_lift_ci_high
    assert result.amount_lift_ci_low_paise <= result.amount_lift_paise <= result.amount_lift_ci_high_paise


def test_deterministic_under_same_seed():
    a = [_row(f"c{i}", "a", 1000, i % 2 == 0) for i in range(40)]
    b = [_row(f"c{i}", "b", 1000, i % 3 == 0) for i in range(40)]
    r1 = paired_bootstrap_lift(a, b, n_bootstrap=500, seed=42)
    r2 = paired_bootstrap_lift(a, b, n_bootstrap=500, seed=42)
    assert r1 == r2


def test_raises_on_no_overlapping_cases():
    a = [_row("only_in_a", "a", 1000, True)]
    b = [_row("only_in_b", "b", 1000, True)]
    with pytest.raises(ValueError):
        paired_bootstrap_lift(a, b)


def test_end_to_end_against_the_real_harness():
    """Not hand-crafted -- runs the actual corpus builder + harness + stats pipeline
    end to end and just confirms it produces sane, internally consistent output."""
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=300, seed=42, batch_simulated_start_at=start)
    results = run_ablation(corpus, [ControlPolicy(), RulesOnlyPolicy()], master_seed=42)

    lift = paired_bootstrap_lift(results["rules_only"], results["control"], seed=7)

    assert lift.n_cases == len(corpus)
    assert 0.0 <= lift.rate_a <= 1.0
    assert 0.0 <= lift.rate_b <= 1.0
    assert lift.rate_lift_ci_low <= lift.rate_lift <= lift.rate_lift_ci_high
    assert lift.amount_lift_ci_low_paise <= lift.amount_lift_paise <= lift.amount_lift_ci_high_paise
