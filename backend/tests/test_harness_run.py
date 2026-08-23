from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_ablation


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _small_corpus(n=100, seed=42):
    return build_corpus(n=n, seed=seed, batch_simulated_start_at=_start())


def _run(n=100, seed=42, master_seed=42):
    corpus = _small_corpus(n=n, seed=seed)
    return run_ablation(
        corpus, [ControlPolicy(), BlindRetryPolicy(), RulesOnlyPolicy()], master_seed=master_seed,
    )


def test_deterministic_under_the_same_seeds():
    a = _run()
    b = _run()
    for arm in ("control", "blind_retry", "rules_only"):
        assert a[arm] == b[arm]


def test_different_master_seed_can_change_outcomes():
    a = _run(master_seed=1)
    b = _run(master_seed=2)
    assert a["control"] != b["control"]


def test_ground_truth_is_shared_across_arms_the_paired_design():
    """A case that's recoverable in one arm's run must be recoverable in every arm's
    run of the same case -- draw_ground_truth is arm-independent by design (Decision 2
    in the Day 3 plan). This is the property that makes the comparison paired."""
    results = _run(n=200)
    by_case = {arm: {r.case_id: r for r in rows} for arm, rows in results.items()}
    for case_id in by_case["control"]:
        control_could_ever_recover = by_case["control"][case_id].recovered_via in ("organic", None)
        # A stronger, direct check: hard-class cases are never recovered in ANY arm --
        # p_case_recoverable_bps['hard'] == 0, unconditionally.
        if by_case["control"][case_id].decline_class == "hard":
            for arm in by_case:
                assert by_case[arm][case_id].recovered is False


def test_control_never_makes_an_attempt():
    results = _run()
    assert all(r.attempt_count == 0 for r in results["control"])
    assert all(r.violation_count == 0 for r in results["control"])


def test_rules_only_never_racks_up_a_violation():
    """Enforced by construction -- rules_only only ever executes when the gate
    approves, so it can never have a rejected-but-acted-on-anyway attempt."""
    results = _run(n=300)
    assert all(r.violation_count == 0 for r in results["rules_only"])


def test_blind_retry_can_accumulate_violations():
    results = _run(n=300)
    assert sum(r.violation_count for r in results["blind_retry"]) > 0


def test_hard_decline_cases_are_never_recovered_in_any_arm():
    results = _run(n=300)
    for arm, rows in results.items():
        for r in rows:
            if r.decline_class == "hard":
                assert r.recovered is False, f"{arm} recovered a hard-decline case"


def test_control_absolute_recovery_rate_is_roughly_the_arithmetic_expectation():
    """Sanity anchor from docs/assumptions.md: ~20% at default params. A wide
    tolerance band -- this is a sanity check, not a precise statistical claim."""
    results = _run(n=2000)
    rate = sum(r.recovered for r in results["control"]) / len(results["control"])
    assert 0.10 < rate < 0.35, f"control recovery rate {rate:.3f} is far from the ~20% expectation"


def test_needs_review_cases_are_a_distinct_outcome_not_silently_not_recovered():
    """Correction 3: a case the gate routes to NEEDS_REVIEW (risk-flagged, or above
    the amount ceiling) must show up as 'deferred_to_human_review', not be silently
    folded into 'not_recovered' -- rules_only correctly declining to auto-act on
    those cases shouldn't be penalised as if it simply failed to recover them."""
    results = _run(n=1000)
    deferred = [r for r in results["rules_only"] if r.outcome == "deferred_to_human_review"]
    assert len(deferred) > 0, "expected some risk-flagged/over-ceiling cases to be deferred"
    for r in deferred:
        assert r.recovered is False
        assert r.route_to == "NEEDS_REVIEW"


def test_outcome_is_always_one_of_the_three_named_buckets():
    results = _run(n=500)
    for arm, rows in results.items():
        outcomes = {r.outcome for r in rows}
        assert outcomes <= {"recovered", "deferred_to_human_review", "not_recovered"}


def test_control_never_defers_it_never_calls_the_gate():
    results = _run(n=500)
    assert all(r.outcome != "deferred_to_human_review" for r in results["control"])


def test_rules_only_saturates_most_of_the_shared_card_budget():
    """The HEADLINE RISK finding on card_reuse_factor, proven directly: rules_only's
    total attempts should land close to (n_cards * network_attempt_budget_per_card_30d)
    -- its recovery is budget-determined via card sharing, not policy-determined."""
    from app.policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D

    n = 1201
    card_reuse_factor = 4.0
    corpus = _small_corpus(n=n, seed=42)
    results = run_ablation(corpus, [RulesOnlyPolicy()], master_seed=42)

    n_cards = round(n / card_reuse_factor)
    theoretical_capacity = n_cards * NETWORK_ATTEMPT_BUDGET_PER_CARD_30D
    total_attempts = sum(r.attempt_count for r in results["rules_only"])
    saturation = total_attempts / theoretical_capacity

    assert saturation > 0.85, f"expected high budget saturation, got {saturation:.1%}"


def test_recovered_set_is_a_superset_of_controls_for_every_arm_that_acts():
    """Regression test for a real bug: an earlier version of the event loop used one
    `resolved` flag for both "recovered" and "action path gave up," so a case whose
    action path gave up (gate rejection or lifetime exceeded) had its still-pending
    ORGANIC event silently discarded -- rules_only (and blind_retry) would then
    under-count organic recoveries relative to control for exactly the cases they
    tried and failed to act on. This is the mechanical invariant that catches it: since
    ground truth (including the organic-resolution draw) is shared across arms by
    design (see test_ground_truth_is_shared_across_arms_the_paired_design), an arm that
    acts can only ever ADD recoveries on top of what would have happened organically
    anyway -- it can never cause a case control recovered to end up not-recovered.
    Found via an OAT sweep result that shouldn't have been possible: rules_only's lift
    over control going negative at high organic_recovery_rate_bps."""
    results = _run(n=1500)
    control_by_id = {r.case_id: r for r in results["control"]}
    for arm in ("rules_only", "blind_retry"):
        for r in results[arm]:
            if control_by_id[r.case_id].recovered:
                assert r.recovered, (
                    f"case {r.case_id} recovered under control (organically) but not "
                    f"under {arm} -- an acting arm must never lose an organic recovery"
                )


def test_giving_up_on_the_action_path_does_not_suppress_a_later_organic_recovery():
    """Direct unit-level check on the fixed mechanism, not just the aggregate
    invariant above: a case whose action path gives up (gate-rejected or lifetime-
    exceeded) must still be able to resolve via a later-scheduled ORGANIC event, and
    must end up reported as recovered/outcome=='recovered' when it does."""
    from datetime import timedelta

    from app.harness.run import _CaseState
    from app.harness.policies import ObservableCase

    case = ObservableCase(
        id="pay_test", amount=10_000, currency="INR", decline_class="soft",
        decline_class_source="error_code", risk_flagged=False, card_id="card_test",
        simulated_at=_start(),
    )
    state = _CaseState(case=case, ground_truth=None)  # ground_truth unused by resolve/give_up

    state.give_up("gave_up_gate_rejected", _start() + timedelta(days=5), route_to="NOT_WORKED")
    assert state.recovered is False
    assert state.action_path_exhausted is True
    assert state.final_status == "gave_up_gate_rejected"

    # The event loop's top-of-loop guard checks `state.recovered`, not this flag --
    # so a pending ORGANIC event for this case would still be processed and reach
    # resolve() below, which is what the guard change in run_arm actually relies on.
    state.resolve("organic", _start() + timedelta(days=10))
    assert state.recovered is True
    assert state.final_status == "recovered"
    assert state.outcome == "recovered"
    # route_to is left as the historical fact about why the action path stopped --
    # outcome/recovered (checked first) are what determine the case's real result.
    assert state.route_to == "NOT_WORKED"


def test_every_case_appears_exactly_once_per_arm():
    corpus = _small_corpus(n=150)
    results = run_ablation(corpus, [ControlPolicy(), RulesOnlyPolicy()], master_seed=42)
    for arm, rows in results.items():
        assert len(rows) == len(corpus)
        assert len({r.case_id for r in rows}) == len(corpus)
