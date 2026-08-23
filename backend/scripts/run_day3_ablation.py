"""Day 3 checkpoint: the real ablation at n>=1000. Per the plan, this stops here —
shown before anything (compliance framing, sweeps) is built on top of these numbers.

Run: cd backend && python -m scripts.run_day3_ablation
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_ablation
from app.harness.stats import paired_bootstrap_lift

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

    print("--- per-arm absolute numbers (not lift -- read these before any lift figure) ---")
    for arm, rows in results.items():
        n_recovered = sum(r.recovered for r in rows)
        total_attempts = sum(r.attempt_count for r in rows)
        total_violations = sum(r.violation_count for r in rows)
        recovered_amount = sum(r.amount_paise for r in rows if r.recovered)
        print(
            f"{arm:>12}: recovery_rate={n_recovered/len(rows):.3%}  "
            f"total_attempts={total_attempts}  total_violations={total_violations}  "
            f"recovered_amount={_fmt_paise(recovered_amount)}"
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


if __name__ == "__main__":
    main()
