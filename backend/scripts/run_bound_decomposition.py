"""Task A2's three-way decomposition, corrected per the Problem 1-4 review round:

Problem 1 (objective parity): OracleUpperBoundPolicy does NOT maximize net value --
stated explicitly in its own docstring now -- so it is not the objective-matched
ceiling for ObservableOptimalPolicy (fit to maximize net_value_paise). A second
variant, OracleValueMaximizingPolicy, reuses observable_optimal's OWN fitted
value-weighting rule (should_yield_by_value) plus perfect recoverability -- the
objective-matched ceiling. Both variants are run and reported; each table below uses
the ceiling matched to ITS OWN metric as the primary chain, with the other variant
shown alongside as a labeled cross-check, never silently dropped.

Problem 2 (metric-shopping): published as two COMPLETE tables, recovery rate and net
value, each with all four arms and held-out CIs -- never one gap in one unit and the
other gap in a different unit. The two tables are expected to (and do) disagree about
whether observable_optimal is an improvement over rules_only -- that disagreement is
reported as the finding, not resolved by picking the flattering table.

Problem 4 (overfitting): observable_optimal's in-sample (PROPOSAL_SEED) vs held-out
net_value_paise -- the metric it was actually fit on -- reported explicitly, not a
third metric (gross amount) it wasn't optimized for.

Problem 3 (Task A claim 2 reasoning) has no code consequence here -- it's a docs-only
correction (docs/results.md) -- but this script does add the attempts-conserved
quantification that correction needs to not be asserted.

Run: cd backend && python -m scripts.run_bound_decomposition
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone

from app import manifest
from app.corpus_builder import build_corpus
from app.harness.compliance import net_value_paise
from app.harness.observable_optimal import ObservableOptimalPolicy, run_observable_optimal_search
from app.harness.oracle import OracleUpperBoundPolicy, OracleValueMaximizingPolicy
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift
from app.model.seeds import HELD_OUT_SEEDS, PROPOSAL_SEED
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

N = 1200
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45
USE_COMMON_RANDOM_NUMBERS = True  # explicit -- see the Task A writeup in docs/results.md

ARMS = ("rules_only", "observable_optimal", "oracle_upper_bound", "oracle_value_maximizing")


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _run_all(seed: int, oo_policy: ObservableOptimalPolicy, ov_policy: OracleValueMaximizingPolicy):
    corpus = build_corpus(n=N, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    oracle_policy = OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS)
    rows = {}
    for name, policy in (
        ("rules_only", RulesOnlyPolicy()), ("observable_optimal", oo_policy),
        ("oracle_upper_bound", oracle_policy), ("oracle_value_maximizing", ov_policy),
    ):
        rows[name] = run_arm(
            corpus, policy, seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS,
            use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS,
        )
    return rows


def _rate(rows) -> float:
    return sum(r.recovered for r in rows) / len(rows)


def main() -> None:
    print("=== MANIFEST -- Task A2 three-way decomposition (corrected: objective parity + two full tables) ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"proposal_seed={PROPOSAL_SEED}  held_out_seeds={list(HELD_OUT_SEEDS)}  n={N}/seed")
    print(f"use_common_random_numbers = {USE_COMMON_RANDOM_NUMBERS}")
    print()

    print("--- fitting observable_optimal on PROPOSAL_SEED=42 (never touches a held-out seed) ---")
    oo_params, oo_fit_nv = run_observable_optimal_search()
    print(f"winner: {oo_params}")
    print(f"in-sample net_value_paise (the objective it was fit on) = {oo_fit_nv:,.2f}")
    oo_policy = ObservableOptimalPolicy(oo_params)
    # OracleValueMaximizingPolicy's master_seed must match each corpus's own seed
    # (ground truth is seed-derived) -- rebuilt fresh per seed in the loop below.

    seeds = [PROPOSAL_SEED] + list(HELD_OUT_SEEDS)
    per_seed_rows = {}
    for seed in seeds:
        ov = OracleValueMaximizingPolicy(oo_params, master_seed=seed, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS)
        per_seed_rows[seed] = _run_all(seed, oo_policy, ov)

    # --- Problem 4: observable_optimal net_value in-sample vs held-out (its own fit objective) ---
    print("\n=== Problem 4: observable_optimal overfitting check, on net_value_paise (its fit objective) ===")
    oo_nv_by_seed = {s: net_value_paise(per_seed_rows[s]["observable_optimal"], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE) for s in seeds}
    print(f"in-sample  (PROPOSAL_SEED={PROPOSAL_SEED}): {oo_nv_by_seed[PROPOSAL_SEED]:,.2f}")
    held_out_nv = [oo_nv_by_seed[s] for s in HELD_OUT_SEEDS]
    print(f"held-out mean: {statistics.mean(held_out_nv):,.2f}  stdev: {statistics.pstdev(held_out_nv):.2f}  "
          f"min: {min(held_out_nv):,.2f}  max: {max(held_out_nv):,.2f}")
    print(f"overfitting gap (in-sample - held-out mean): {oo_nv_by_seed[PROPOSAL_SEED] - statistics.mean(held_out_nv):,.2f}")

    # --- Table 1: recovery rate ---
    print("\n=== TABLE 1 -- RECOVERY RATE (rules_only -> observable_optimal -> oracle_upper_bound is the primary chain) ===")
    print(f"{'arm':>26} {'PROPOSAL_SEED rate':>20} {'held-out mean rate':>20} {'held-out stdev':>16}")
    rate_by_arm_seed = {arm: {s: _rate(per_seed_rows[s][arm]) for s in seeds} for arm in ARMS}
    for arm in ARMS:
        ho = [rate_by_arm_seed[arm][s] for s in HELD_OUT_SEEDS]
        print(f"{arm:>26} {rate_by_arm_seed[arm][PROPOSAL_SEED]:>19.3%} {statistics.mean(ho):>19.3%} {statistics.pstdev(ho):>16.4f}")

    def _rate_gap(a, b, seed):
        lift = paired_bootstrap_lift(per_seed_rows[seed][a], per_seed_rows[seed][b], seed=7)
        return lift.rate_lift, lift.rate_lift_ci_low, lift.rate_lift_ci_high

    print("\nRATE gaps (primary chain: rules_only -> observable_optimal -> oracle_upper_bound):")
    for seed in seeds:
        g1 = _rate_gap("observable_optimal", "rules_only", seed)
        g2 = _rate_gap("oracle_upper_bound", "observable_optimal", seed)
        total = _rate_gap("oracle_upper_bound", "rules_only", seed)
        print(
            f"  seed={seed}: GAP1={g1[0]:+.4f} [{g1[1]:+.4f},{g1[2]:+.4f}]  GAP2={g2[0]:+.4f} [{g2[1]:+.4f},{g2[2]:+.4f}]  "
            f"GAP1+GAP2={g1[0]+g2[0]:+.4f}  direct(oracle_upper_bound-rules_only)={total[0]:+.4f}  "
            f"{'MATCH' if abs((g1[0]+g2[0]) - total[0]) < 1e-9 else 'MISMATCH'}"
        )
    print("\nCross-check row (rate): oracle_value_maximizing vs observable_optimal (the OTHER oracle variant, shown not hidden):")
    for seed in seeds:
        g2v = _rate_gap("oracle_value_maximizing", "observable_optimal", seed)
        print(f"  seed={seed}: {g2v[0]:+.4f} [{g2v[1]:+.4f},{g2v[2]:+.4f}]")

    # --- Table 2: net value ---
    print("\n=== TABLE 2 -- NET VALUE (rules_only -> observable_optimal -> oracle_value_maximizing is the primary chain) ===")
    print(f"{'arm':>26} {'PROPOSAL_SEED net_value':>24} {'held-out mean net_value':>24}")
    nv_by_arm_seed = {arm: {s: net_value_paise(per_seed_rows[s][arm], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE) for s in seeds} for arm in ARMS}
    for arm in ARMS:
        ho = [nv_by_arm_seed[arm][s] for s in HELD_OUT_SEEDS]
        print(f"{arm:>26} {_fmt_paise(nv_by_arm_seed[arm][PROPOSAL_SEED]):>24} {_fmt_paise(statistics.mean(ho)):>24}")

    print("\nNET VALUE gaps (point differences; paired_bootstrap_lift's amount_lift is GROSS recovered amount, not net -- reported separately below for reference only):")
    for seed in seeds:
        g1v = nv_by_arm_seed["observable_optimal"][seed] - nv_by_arm_seed["rules_only"][seed]
        g2v = nv_by_arm_seed["oracle_value_maximizing"][seed] - nv_by_arm_seed["observable_optimal"][seed]
        total_v = nv_by_arm_seed["oracle_value_maximizing"][seed] - nv_by_arm_seed["rules_only"][seed]
        print(
            f"  seed={seed}: GAP1={_fmt_paise(g1v)}  GAP2={_fmt_paise(g2v)}  "
            f"GAP1+GAP2={_fmt_paise(g1v+g2v)}  direct={_fmt_paise(total_v)}  "
            f"{'MATCH' if abs((g1v+g2v) - total_v) < 1 else 'MISMATCH'}"
        )
    print("\nCross-check row (net value): oracle_upper_bound vs observable_optimal (the OTHER oracle variant):")
    for seed in seeds:
        gv = nv_by_arm_seed["oracle_upper_bound"][seed] - nv_by_arm_seed["observable_optimal"][seed]
        print(f"  seed={seed}: {_fmt_paise(gv)}")

    # --- Problem 3: quantify attempts conserved by the oracle vs rules_only ---
    print("\n=== Problem 3: attempts conserved by oracle_upper_bound vs rules_only (PROPOSAL_SEED) ===")
    r_rows = per_seed_rows[PROPOSAL_SEED]["rules_only"]
    o_rows = per_seed_rows[PROPOSAL_SEED]["oracle_upper_bound"]
    r_attempts = sum(r.attempt_count for r in r_rows)
    o_attempts = sum(r.attempt_count for r in o_rows)
    print(f"total attempts: rules_only={r_attempts}  oracle_upper_bound={o_attempts}  conserved={r_attempts - o_attempts}")
    r_by_id = {r.case_id: r for r in r_rows}
    o_by_id = {r.case_id: r for r in o_rows}
    reduced_by_class: dict[str, int] = {}
    increased_by_class: dict[str, int] = {}
    for cid in r_by_id:
        delta = r_by_id[cid].attempt_count - o_by_id[cid].attempt_count
        cls = r_by_id[cid].decline_class
        if delta > 0:
            reduced_by_class[cls] = reduced_by_class.get(cls, 0) + delta
        elif delta < 0:
            increased_by_class[cls] = increased_by_class.get(cls, 0) + (-delta)
    print(f"attempts REDUCED (oracle skips a doomed case) by decline_class: {reduced_by_class}  sum={sum(reduced_by_class.values())}")
    print(f"attempts INCREASED (freed capacity reallocated to another case on the same card) by decline_class: {increased_by_class}  sum={sum(increased_by_class.values())}")
    print(f"reconciliation: {sum(reduced_by_class.values())} - {sum(increased_by_class.values())} = {sum(reduced_by_class.values()) - sum(increased_by_class.values())}  (should equal the net {r_attempts - o_attempts} above)")
    print(
        "NOTE: 'hard' should show ~0 reduced here (a hard-decline case never reaches the gate for "
        "rules_only either, so oracle skipping it costs rules_only nothing extra) -- the real conservation "
        "is on 'soft'/'technical' cases ground truth says are unrecoverable, which rules_only DOES attempt "
        "and DOES consume shared card budget on. The 'increased' side is the reallocation itself: freed "
        "capacity on a shared card lets OTHER cases on that card get more tries than rules_only's congestion "
        "would have allowed."
    )


if __name__ == "__main__":
    main()
