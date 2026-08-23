from datetime import datetime, timezone

import pytest

from app.corpus_builder import build_corpus
from app.harness.compliance import break_even_penalty_paise, net_value_paise, total_violations
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import CaseArmResult, run_ablation
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE


def _row(case_id, arm, amount, recovered, attempts, violations):
    return CaseArmResult(
        case_id=case_id, arm=arm, amount_paise=amount, decline_class="soft",
        recovered=recovered, recovered_via="action" if recovered else None,
        resolved_at=None, attempt_count=attempts, violation_count=violations,
        final_status="recovered" if recovered else "not_recovered",
        route_to=None, outcome="recovered" if recovered else "not_recovered",
    )


def test_net_value_hand_computed():
    """cost = 1000 milli-paise = Re1.00/attempt exactly, chosen so the arithmetic is
    checkable by hand: 2 recovered cases (10000 + 20000 = 30000 paise), 10 attempts
    total -> contact cost 10 paise -> net value 29990 paise."""
    rows = [
        _row("a", "blind_retry", 10_000, True, 5, 4),
        _row("b", "blind_retry", 20_000, True, 5, 4),
    ]
    assert net_value_paise(rows, cost_per_contact_attempt_milli_paise=1000) == pytest.approx(29_990)


def test_break_even_penalty_hand_computed():
    """Full hand-computed example, cost=1000 milli-paise (Re1.00/attempt):
    blind_retry: 2 cases recovered (10000+20000=30000 paise), 10 attempts, 8 violations
      -> net = 30000 - 10*1 = 29990
    rules_only: 1 case recovered (10000 paise), 3 attempts, 0 violations
      -> net = 10000 - 3*1 = 9997
    penalty_break_even = (29990 - 9997) / 8 = 19993 / 8 = 2499.125 paise/violation
    """
    blind_rows = [
        _row("a", "blind_retry", 10_000, True, 5, 4),
        _row("b", "blind_retry", 20_000, True, 5, 4),
        _row("c", "blind_retry", 0, False, 0, 0),
    ]
    rules_rows = [
        _row("a", "rules_only", 10_000, True, 3, 0),
        _row("b", "rules_only", 0, False, 0, 0),
        _row("c", "rules_only", 0, False, 0, 0),
    ]
    assert total_violations(blind_rows) == 8
    assert total_violations(rules_rows) == 0

    penalty = break_even_penalty_paise(rules_rows, blind_rows, cost_per_contact_attempt_milli_paise=1000)
    assert penalty == pytest.approx(2499.125)


def test_break_even_penalty_raises_if_enforced_arm_has_violations():
    with pytest.raises(ValueError):
        break_even_penalty_paise(
            [_row("a", "rules_only", 100, False, 1, 1)],
            [_row("a", "blind_retry", 100, False, 1, 1)],
            cost_per_contact_attempt_milli_paise=1000,
        )


def test_break_even_penalty_raises_if_audit_only_arm_has_no_violations():
    with pytest.raises(ValueError):
        break_even_penalty_paise(
            [_row("a", "rules_only", 100, False, 1, 0)],
            [_row("a", "blind_retry", 100, False, 1, 0)],
            cost_per_contact_attempt_milli_paise=1000,
        )


def test_ignoring_contact_cost_would_overstate_the_penalty_the_bug_correction_1():
    """Proves correction 1's point directly: computing on gross recovered amount
    (ignoring attempt cost) gives a HIGHER penalty rate than the correct net-value
    calculation, because blind_retry's much larger attempt count is a real cost the
    gross figure hides."""
    blind_rows = [
        _row("a", "blind_retry", 10_000, True, 5, 4),
        _row("b", "blind_retry", 20_000, True, 5, 4),
    ]
    rules_rows = [_row("a", "rules_only", 10_000, True, 3, 0)]

    gross_penalty = (
        sum(r.amount_paise for r in blind_rows if r.recovered)
        - sum(r.amount_paise for r in rules_rows if r.recovered)
    ) / total_violations(blind_rows)
    net_penalty = break_even_penalty_paise(rules_rows, blind_rows, cost_per_contact_attempt_milli_paise=1000)

    assert net_penalty < gross_penalty


def test_end_to_end_against_the_real_harness_produces_a_finite_positive_penalty():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=1201, seed=42, batch_simulated_start_at=start)
    results = run_ablation(
        corpus, [ControlPolicy(), BlindRetryPolicy(), RulesOnlyPolicy()], master_seed=42,
    )
    penalty = break_even_penalty_paise(
        results["rules_only"], results["blind_retry"], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
    )
    assert penalty > 0
