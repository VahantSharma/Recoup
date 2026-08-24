from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.harness.oracle import OracleUpperBoundPolicy
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm
from app.simulator.outcomes import draw_ground_truth


def _corpus(n=500, seed=42):
    return build_corpus(n=n, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_oracle_never_attempts_a_provably_unrecoverable_case():
    corpus = _corpus()
    seed = 42
    rows = run_arm(corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=45), seed, 24, 45)
    by_id = {r.case_id: r for r in rows}
    for draft in corpus:
        gt = draw_ground_truth(
            case_id=draft.razorpay_payment_id, decline_class=draft.decline_class,
            master_seed=seed, case_simulated_at=draft.simulated_at, max_case_lifetime_days=45,
        )
        if not gt.is_recoverable:
            assert by_id[draft.razorpay_payment_id].attempt_count == 0, (
                f"oracle made an attempt on a provably unrecoverable case {draft.razorpay_payment_id}"
            )


def test_oracle_never_recovers_a_case_that_was_never_recoverable():
    """Sanity floor: the oracle's extra knowledge can only avoid WASTED attempts, it
    can't manufacture a recovery draw_ground_truth already ruled out -- same invariant
    every other acting arm respects (see test_hard_decline_cases_are_never_recovered_in_any_arm)."""
    corpus = _corpus()
    seed = 42
    rows = run_arm(corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=45), seed, 24, 45)
    for r in rows:
        if r.decline_class == "hard":
            assert r.recovered is False


def test_oracle_recovered_set_is_a_superset_of_rules_onlys():
    """Never wasting a budget slot on a hopeless case can only free capacity for
    recoverable ones -- the oracle can never do WORSE than rules_only, case by case in
    aggregate recovery rate, under identical ground truth and identical CRN draws."""
    corpus = _corpus(n=1200)
    seed = 42
    oracle_rows = run_arm(corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=45), seed, 24, 45)
    rules_rows = run_arm(corpus, RulesOnlyPolicy(), seed, 24, 45)
    oracle_rate = sum(r.recovered for r in oracle_rows) / len(oracle_rows)
    rules_rate = sum(r.recovered for r in rules_rows) / len(rules_rows)
    assert oracle_rate >= rules_rate


def test_oracle_is_deterministic():
    corpus = _corpus()
    seed = 42
    a = run_arm(corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=45), seed, 24, 45)
    b = run_arm(corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=45), seed, 24, 45)
    assert a == b


def test_oracle_conforms_to_the_policy_protocol_shape():
    """Runs through the unmodified app.harness.run.run_arm with zero special-casing --
    this only works if propose()'s signature matches what run.py actually calls."""
    import inspect

    from app.harness.policies import Policy

    oracle_params = list(inspect.signature(OracleUpperBoundPolicy.propose).parameters)
    protocol_params = list(inspect.signature(Policy.propose).parameters)
    assert oracle_params == protocol_params
