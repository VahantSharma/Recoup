"""The direct proof that the common-random-numbers fix (app.simulator.outcomes.
attempt_succeeds) actually restores pairing, and a measurement of how much noise the
old (pre-fix) behavior injected. See docs/results.md's "Common random numbers"
section for the full narrative -- this file is the evidence, not just a claim.

The null-arm test: run the SAME decision logic (RulesOnlyPolicy's propose(), copied
into a tiny local class so its `name` is settable) twice, under two different arm
names, over the same corpus and master_seed. Two arms that make IDENTICAL decisions on
every case must, under a correctly-paired design, produce IDENTICAL outcomes -- not
"a lift whose 95% CI happens to contain zero," but an EXACT, deterministic zero, case
by case. Any nonzero difference between two policies whose propose() logic is
byte-for-byte identical can only be attributable to the RNG stream depending on
something it structurally should not depend on (here: `arm`). That's a much stronger
and more direct test than a bootstrap CI, and it's what "null arm" means in this file.

use_common_random_numbers=False reproduces the pre-fix behavior and is kept runnable
for exactly one purpose: measuring what the old harness's noise floor actually was, so
the claim "the old design was noisier" is a measured number, not an assertion.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.gate import ActionProposal
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift


class _NamedRulesLikePolicy:
    """Identical propose() logic to app.harness.policies.RulesOnlyPolicy, with a
    settable name -- isolates exactly one variable (the arm name) between two
    otherwise-identical policies, which is what makes this a clean null-arm test."""

    def __init__(self, name: str):
        self.name = name

    def propose(self, case, history, now, card_attempts_in_window):
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)


def _corpus(n=1200, seed=42):
    return build_corpus(n=n, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def _run(name: str, use_common_random_numbers: bool, corpus):
    return run_arm(
        corpus, _NamedRulesLikePolicy(name), master_seed=42,
        retry_delay_hours=24, max_case_lifetime_days=45,
        use_common_random_numbers=use_common_random_numbers,
    )


def test_null_arm_is_exactly_zero_under_common_random_numbers():
    corpus = _corpus()
    rows_a = _run("null_arm_a", True, corpus)
    rows_b = _run("null_arm_b", True, corpus)

    by_id_a = {r.case_id: r for r in rows_a}
    by_id_b = {r.case_id: r for r in rows_b}
    assert set(by_id_a) == set(by_id_b)

    mismatches = []
    for case_id in by_id_a:
        a, b = by_id_a[case_id], by_id_b[case_id]
        if (a.recovered, a.attempt_count, a.amount_paise, a.final_status, a.resolved_at) != (
            b.recovered, b.attempt_count, b.amount_paise, b.final_status, b.resolved_at,
        ):
            mismatches.append(case_id)
    assert not mismatches, (
        f"{len(mismatches)} case(s) diverged between two identically-behaving arms "
        f"under common random numbers -- pairing is broken: {mismatches[:5]}"
    )

    lift = paired_bootstrap_lift(rows_a, rows_b, seed=7)
    assert lift.rate_lift == 0.0
    assert lift.rate_lift_ci_low == 0.0
    assert lift.rate_lift_ci_high == 0.0
    assert lift.amount_lift_paise == 0
    assert lift.amount_lift_ci_low_paise == 0.0
    assert lift.amount_lift_ci_high_paise == 0.0


def test_null_arm_noise_floor_without_common_random_numbers():
    """Measures, doesn't guess, the pre-fix design's empirical noise floor: two
    identically-behaving arms, same corpus, same master_seed, arm-keyed RNG (the old
    default). Observed once at n=1201, master_seed=42 (this test's exact parameters):
    74/1201 (6.2%) recovered-outcome mismatches, 474/1201 (39.5%) attempt_count
    mismatches, rate_lift=-0.0050 with a 95% CI about 0.03 wide -- CI width alone is
    the noise floor's signature (a true null arm's CI should collapse to a point, per
    the exact-zero test above; this ~0.03-wide band is what the old, unfixed seeding
    added on top of every real arm-vs-arm comparison in the project so far, including
    Day 3's headline numbers). Only the *direction* (mismatches > 0) is asserted below,
    not the exact counts -- pinning exact counts would make this test brittle to
    unrelated corpus-builder changes without adding real protection."""
    corpus = _corpus()
    rows_a = _run("null_arm_a", False, corpus)
    rows_b = _run("null_arm_b", False, corpus)

    by_id_a = {r.case_id: r for r in rows_a}
    by_id_b = {r.case_id: r for r in rows_b}
    n_recovered_mismatches = sum(
        1 for cid in by_id_a if by_id_a[cid].recovered != by_id_b[cid].recovered
    )
    n_attempt_count_mismatches = sum(
        1 for cid in by_id_a if by_id_a[cid].attempt_count != by_id_b[cid].attempt_count
    )

    lift = paired_bootstrap_lift(rows_a, rows_b, seed=7)

    print(f"\nnoise floor (use_common_random_numbers=False, n={len(corpus)}):")
    print(f"  recovered-outcome mismatches: {n_recovered_mismatches}")
    print(f"  attempt_count mismatches:     {n_attempt_count_mismatches}")
    print(f"  rate_lift: {lift.rate_lift:+.4f}  95% CI [{lift.rate_lift_ci_low:+.4f}, {lift.rate_lift_ci_high:+.4f}]")

    # Regression-locked: two policies with IDENTICAL decision logic must show real
    # divergence under the old, arm-keyed seeding -- this is the noise the CRN fix
    # eliminates. A future accidental revert of the fix would make this test's own
    # "not exactly zero" assertion below start failing loudly only if divergence
    # somehow vanished; the real guard against a silent revert is the exact-zero test
    # above, which would immediately fail instead.
    assert n_recovered_mismatches > 0, "expected the old, unfixed seeding to show real divergence between identical policies"
    assert lift.rate_lift != 0.0
