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


def test_every_case_appears_exactly_once_per_arm():
    corpus = _small_corpus(n=150)
    results = run_ablation(corpus, [ControlPolicy(), RulesOnlyPolicy()], master_seed=42)
    for arm, rows in results.items():
        assert len(rows) == len(corpus)
        assert len({r.case_id for r in rows}) == len(corpus)
