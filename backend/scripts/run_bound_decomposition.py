"""Task A2's three-way decomposition, replacing the narrower run_oracle_headroom.py.
Fixes Task A's auditability gap too: use_common_random_numbers is now explicit and
printed in the manifest (it was already True by default before -- the audit found
this correct-but-implicit, not incorrect; see docs/results.md's Task A writeup).

Three policies, same corpus/seed/CRN throughout:
  rules_only          -- the real, enforced, submittable arm (unchanged)
  observable_optimal  -- analysis-only ceiling using ONLY features a real system has
                          at decision time (app.harness.observable_optimal); fit by
                          deterministic search on PROPOSAL_SEED=42
  oracle_upper_bound  -- analysis-only ceiling using PERFECT ground-truth
                          recoverability (app.harness.oracle); ceiling on ANY policy,
                          observable or not

Reports both gaps, each with a paired-bootstrap CI, at PROPOSAL_SEED and across all 10
HELD_OUT_SEEDS -- one point estimate would repeat the mistake the multi-seed design
elsewhere in this project exists to avoid.

Run: cd backend && python -m scripts.run_bound_decomposition
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app import manifest
from app.corpus_builder import build_corpus
from app.harness.compliance import net_value_paise
from app.harness.observable_optimal import ObservableOptimalPolicy, run_observable_optimal_search
from app.harness.oracle import OracleUpperBoundPolicy
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift
from app.model.seeds import HELD_OUT_SEEDS, PROPOSAL_SEED
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

N = 1200
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45
USE_COMMON_RANDOM_NUMBERS = True  # explicit -- see the Task A writeup in docs/results.md


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _run_three(seed: int, oo_policy: ObservableOptimalPolicy):
    corpus = build_corpus(n=N, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    rules_rows = run_arm(corpus, RulesOnlyPolicy(), seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS)
    oo_rows = run_arm(corpus, oo_policy, seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS)
    oracle_rows = run_arm(
        corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS),
        seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS,
    )
    return rules_rows, oo_rows, oracle_rows


def main() -> None:
    print("=== MANIFEST -- Task A2 three-way bound decomposition ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"proposal_seed={PROPOSAL_SEED}  held_out_seeds={list(HELD_OUT_SEEDS)}  n={N}/seed")
    print(f"use_common_random_numbers = {USE_COMMON_RANDOM_NUMBERS}")
    print()

    print("--- fitting observable_optimal on PROPOSAL_SEED=42 (never touches a held-out seed) ---")
    oo_params, oo_fit_nv = run_observable_optimal_search()
    print(f"winner: {oo_params}")
    print(f"in-sample net_value_paise = {oo_fit_nv:,.2f}")
    oo_policy = ObservableOptimalPolicy(oo_params)

    print(f"\n--- PROPOSAL_SEED={PROPOSAL_SEED} (in-sample point) ---")
    rules_rows, oo_rows, oracle_rows = _run_three(PROPOSAL_SEED, oo_policy)
    rules_nv = net_value_paise(rules_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    oo_nv = net_value_paise(oo_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    oracle_nv = net_value_paise(oracle_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    lift_gap1 = paired_bootstrap_lift(oo_rows, rules_rows, seed=7)
    lift_gap2 = paired_bootstrap_lift(oracle_rows, oo_rows, seed=7)
    print(f"recovery rate: rules_only={lift_gap1.rate_b:.3%}  observable_optimal={lift_gap1.rate_a:.3%}  oracle={lift_gap2.rate_a:.3%}")
    print(f"net_value: rules_only={_fmt_paise(rules_nv)}  observable_optimal={_fmt_paise(oo_nv)}  oracle={_fmt_paise(oracle_nv)}")
    print(f"GAP 1 (observable_optimal - rules_only): rate_lift={lift_gap1.rate_lift:+.4f}  95% CI [{lift_gap1.rate_lift_ci_low:+.4f}, {lift_gap1.rate_lift_ci_high:+.4f}]")
    print(f"         GROSS recovered-amount_lift={_fmt_paise(lift_gap1.amount_lift_paise)}  95% CI [{_fmt_paise(lift_gap1.amount_lift_ci_low_paise)}, {_fmt_paise(lift_gap1.amount_lift_ci_high_paise)}]  (gross, NOT net of attempt cost)")
    print(
        "         NOTE: observable_optimal was fit to maximize NET value_paise (recovered amount minus "
        "attempt cost -- same objective as the grid search), not recovery RATE or gross amount. A negative "
        "rate_lift alongside a positive net_value point-estimate (below) means it recovers FEWER cases but "
        "MORE net rupees at fewer total attempts -- a real value-maximizing tradeoff (yielding scarce budget "
        "away from smaller/marginal/stale cases toward bigger tickets), not a worse policy on the metric it "
        "was actually optimized against. See docs/results.md for the diagnosed mechanism (avg recovered "
        "ticket size, attempt count) behind this specific run."
    )
    print(f"GAP 2 (oracle - observable_optimal):      rate_lift={lift_gap2.rate_lift:+.4f}  95% CI [{lift_gap2.rate_lift_ci_low:+.4f}, {lift_gap2.rate_lift_ci_high:+.4f}]")
    print(f"         (oracle - observable_optimal):      amount_lift={_fmt_paise(lift_gap2.amount_lift_paise)}  95% CI [{_fmt_paise(lift_gap2.amount_lift_ci_low_paise)}, {_fmt_paise(lift_gap2.amount_lift_ci_high_paise)}]")

    print(f"\n--- across all {len(HELD_OUT_SEEDS)} held-out seeds (oo_params frozen from the PROPOSAL_SEED fit above) ---")
    gap1_deltas, gap2_deltas, gap1_amount_deltas = [], [], []
    for seed in HELD_OUT_SEEDS:
        r_rows, o_rows, orc_rows = _run_three(seed, oo_policy)
        g1 = paired_bootstrap_lift(o_rows, r_rows, seed=7)
        g2 = paired_bootstrap_lift(orc_rows, o_rows, seed=7)
        gap1_deltas.append(g1.rate_lift)
        gap2_deltas.append(g2.rate_lift)
        gap1_amount_deltas.append(g1.amount_lift_paise)
        print(
            f"seed={seed}: GAP1(oo-rules) rate={g1.rate_lift:+.4f} [{g1.rate_lift_ci_low:+.4f},{g1.rate_lift_ci_high:+.4f}]  "
            f"amount={_fmt_paise(g1.amount_lift_paise)}  "
            f"GAP2(oracle-oo)={g2.rate_lift:+.4f} [{g2.rate_lift_ci_low:+.4f},{g2.rate_lift_ci_high:+.4f}]"
        )

    print(f"\nGAP 1 (observable_optimal - rules_only) RATE distribution: mean={statistics.mean(gap1_deltas):+.4f}  stdev={statistics.pstdev(gap1_deltas):.4f}  min={min(gap1_deltas):+.4f}  max={max(gap1_deltas):+.4f}")
    print(f"GAP 1 (observable_optimal - rules_only) AMOUNT distribution: mean={_fmt_paise(statistics.mean(gap1_amount_deltas))}  positive (higher net value) in {sum(d > 0 for d in gap1_amount_deltas)}/{len(gap1_amount_deltas)} seeds")
    print(f"GAP 2 (oracle - observable_optimal) RATE distribution:      mean={statistics.mean(gap2_deltas):+.4f}  stdev={statistics.pstdev(gap2_deltas):.4f}  min={min(gap2_deltas):+.4f}  max={max(gap2_deltas):+.4f}")


if __name__ == "__main__":
    main()
