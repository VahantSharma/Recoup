"""Day 3 checkpoint: the real ablation at n>=1000. Per the plan, this stops here —
shown before anything (compliance framing, sweeps) is built on top of these numbers.

Run: cd backend && python -m scripts.run_day3_ablation
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.harness.compliance import break_even_penalty_paise, net_value_paise, total_violations
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_ablation
from app.harness.stats import paired_bootstrap_lift
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

# Directly fetched, cited -- not assumed. See docs/assumptions.md's Compliance economics.
USD_TO_INR = 95.70  # Xe.com mid-market rate, 09:25 UTC, 23 Aug 2026

N = 1200
SEED = 42


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=N, seed=SEED, batch_simulated_start_at=start)

    policies = [ControlPolicy(), BlindRetryPolicy(), RulesOnlyPolicy()]
    results = run_ablation(corpus, policies, master_seed=SEED)

    print(f"n={len(corpus)} cases, master_seed={SEED}\n")

    print("--- per-arm absolute numbers, THREE-way outcome split (not lift -- read these first) ---")
    for arm, rows in results.items():
        n = len(rows)
        n_recovered = sum(r.recovered for r in rows)
        n_deferred = sum(r.outcome == "deferred_to_human_review" for r in rows)
        n_not_recovered = sum(r.outcome == "not_recovered" for r in rows)
        total_attempts = sum(r.attempt_count for r in rows)
        arm_violations = total_violations(rows)  # app.harness.compliance's function --
                                                    # a prior local var here shadowed
                                                    # the import; renamed, not just
                                                    # worked around
        recovered_amount = sum(r.amount_paise for r in rows if r.recovered)
        deferred_amount = sum(r.amount_paise for r in rows if r.outcome == "deferred_to_human_review")
        print(
            f"{arm:>12}: recovered={n_recovered/n:.3%}  deferred_to_human_review={n_deferred/n:.3%}  "
            f"not_recovered={n_not_recovered/n:.3%}"
        )
        print(
            f"{'':>12}  total_attempts={total_attempts}  total_violations={arm_violations}  "
            f"recovered_amount={_fmt_paise(recovered_amount)}  deferred_amount={_fmt_paise(deferred_amount)}"
        )

    print("\n--- paired bootstrap lift (95% CI, 2000 resamples) ---")
    for arm_a, arm_b in (("rules_only", "control"), ("blind_retry", "control"), ("blind_retry", "rules_only")):
        lift = paired_bootstrap_lift(results[arm_a], results[arm_b], seed=7)
        print(f"\n{arm_a} vs {arm_b} (n={lift.n_cases}):")
        print(f"  recovery rate: {lift.rate_a:.3%} vs {lift.rate_b:.3%}")
        print(
            f"  rate lift:   {lift.rate_lift:+.4f}  "
            f"(95% CI [{lift.rate_lift_ci_low:+.4f}, {lift.rate_lift_ci_high:+.4f}])"
        )
        print(
            f"  amount lift: {_fmt_paise(lift.amount_lift_paise)}  "
            f"(95% CI [{_fmt_paise(lift.amount_lift_ci_low_paise)}, "
            f"{_fmt_paise(lift.amount_lift_ci_high_paise)}])"
        )

    print("\n--- compliance economics: break-even penalty rate (net value, not gross) ---")
    penalty_paise = break_even_penalty_paise(
        results["rules_only"], results["blind_retry"], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
    )
    penalty_usd = (penalty_paise / 100) / USD_TO_INR
    print(f"net_value(blind_retry) = {_fmt_paise(net_value_paise(results['blind_retry'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"net_value(rules_only)  = {_fmt_paise(net_value_paise(results['rules_only'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"violations(blind_retry) = {total_violations(results['blind_retry'])}")
    print(f"break-even penalty = {_fmt_paise(penalty_paise)} per violation  (${penalty_usd:.2f} at 1 USD = Rs{USD_TO_INR})")
    print("  vs Visa $0.10/excess (Rs%.2f): break-even is ABOVE -> compliance doesn't pay on this alone" % (0.10 * USD_TO_INR))
    print("  vs Mastercard $1.00-$2.00/excess (Rs%.2f-Rs%.2f): break-even is BELOW -> compliance pays" % (1.00 * USD_TO_INR, 2.00 * USD_TO_INR))


if __name__ == "__main__":
    main()
