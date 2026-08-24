"""oracle_upper_bound - rules_only: the honest ceiling for whatever ANY allocator
working through the yield-at-scarcity mechanism (app.harness.policies.
ModelPlaybookPolicy) could ever find, given perfect per-case recoverability
information instead of a blind per-class heuristic. See app/harness/oracle.py's
module docstring for the full construction and its explicit scope (a ceiling, not
THE global optimum).

Runs at PROPOSAL_SEED (the same corpus Day 4's grid search and synthesis draw on) and
across all 10 HELD_OUT_SEEDS, paired bootstrap lift with CI throughout -- one point
estimate would repeat exactly the mistake the multi-seed design elsewhere in this
project exists to avoid.

Run: cd backend && python -m scripts.run_oracle_headroom
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app import manifest
from app.corpus_builder import build_corpus
from app.harness.compliance import net_value_paise
from app.harness.oracle import OracleUpperBoundPolicy
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift
from app.model.seeds import HELD_OUT_SEEDS, PROPOSAL_SEED
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

N = 1200
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _run_one(seed: int) -> tuple:
    corpus = build_corpus(n=N, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    oracle_rows = run_arm(
        corpus, OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS),
        seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS,
    )
    rules_rows = run_arm(corpus, RulesOnlyPolicy(), seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS)
    return oracle_rows, rules_rows


def main() -> None:
    print("=== MANIFEST -- oracle_upper_bound headroom (Task 2) ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"proposal_seed={PROPOSAL_SEED}  held_out_seeds={list(HELD_OUT_SEEDS)}  n={N}/seed")
    print()

    print(f"--- PROPOSAL_SEED={PROPOSAL_SEED} (same corpus grid search/synthesis draw on) ---")
    oracle_rows, rules_rows = _run_one(PROPOSAL_SEED)
    lift = paired_bootstrap_lift(oracle_rows, rules_rows, seed=7)
    oracle_nv = net_value_paise(oracle_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    rules_nv = net_value_paise(rules_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    print(f"recovery rate: oracle={lift.rate_a:.3%}  rules_only={lift.rate_b:.3%}")
    print(f"rate_lift: {lift.rate_lift:+.4f}  95% CI [{lift.rate_lift_ci_low:+.4f}, {lift.rate_lift_ci_high:+.4f}]")
    print(f"amount_lift: {_fmt_paise(lift.amount_lift_paise)}  95% CI [{_fmt_paise(lift.amount_lift_ci_low_paise)}, {_fmt_paise(lift.amount_lift_ci_high_paise)}]")
    print(f"net_value: oracle={_fmt_paise(oracle_nv)}  rules_only={_fmt_paise(rules_nv)}  gap={_fmt_paise(oracle_nv - rules_nv)}")
    oracle_yield_avoided = sum(1 for r in oracle_rows if r.attempt_count == 0) - sum(1 for r in rules_rows if r.attempt_count == 0)
    print(f"cases with zero attempts, oracle vs rules_only: {sum(1 for r in oracle_rows if r.attempt_count == 0)} vs {sum(1 for r in rules_rows if r.attempt_count == 0)}")

    print(f"\n--- across all {len(HELD_OUT_SEEDS)} held-out seeds ---")
    rate_deltas = []
    for seed in HELD_OUT_SEEDS:
        o_rows, r_rows = _run_one(seed)
        l = paired_bootstrap_lift(o_rows, r_rows, seed=7)
        rate_deltas.append(l.rate_lift)
        print(f"seed={seed}: rate_lift={l.rate_lift:+.4f}  95% CI [{l.rate_lift_ci_low:+.4f}, {l.rate_lift_ci_high:+.4f}]")

    print(f"\nheld-out rate_lift distribution: mean={statistics.mean(rate_deltas):+.4f}  "
          f"stdev={statistics.pstdev(rate_deltas):.4f}  min={min(rate_deltas):+.4f}  max={max(rate_deltas):+.4f}")


if __name__ == "__main__":
    main()
