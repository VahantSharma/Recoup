"""Re-checks Day 3's HEADLINE ablation table and single-point compliance-economics
figure under the common-random-numbers fix (app.simulator.outcomes.attempt_succeeds),
side by side with the exact pre-fix numbers, without touching
scripts/run_day3_ablation.py or any figure already committed in docs/results.md's
"## Day 3" section -- those stay exactly as originally run and reported, per their own
"one run manifest" discipline. This script's job is narrower and explicitly additive:
does the CRN fix change Day 3's headline claims, and if so by how much.

Does NOT re-run Day 3's 15-parameter OAT/joint sensitivity sweep (500+ draws each) --
that is a real, separately-scoped follow-up, not done in this pass. Flagged here
rather than silently left undone.

Same N, SEED, and corpus/policy parameters as scripts/run_day3_ablation.py, so the two
runs are comparable except for the one variable under test (use_common_random_numbers).

Run: cd backend && python -m scripts.run_day3_headline_crn_recheck
"""
from __future__ import annotations

from datetime import datetime, timezone

from app import manifest
from app.corpus_builder import build_corpus
from app.harness.compliance import break_even_penalty_paise, net_value_paise, total_violations
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift
from app.policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

USD_TO_INR = 95.70  # same cited rate Day 3 used -- see docs/assumptions.md

N = 1200
SEED = 42
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _run_all_arms(corpus, use_common_random_numbers: bool) -> dict:
    return {
        "control": run_arm(corpus, ControlPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=use_common_random_numbers),
        "blind_retry": run_arm(corpus, BlindRetryPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=use_common_random_numbers),
        "rules_only": run_arm(corpus, RulesOnlyPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS, use_common_random_numbers=use_common_random_numbers),
    }


def _print_headline(label: str, results: dict) -> None:
    print(f"--- {label}: three-way outcome split ---")
    for arm, rows in results.items():
        n = len(rows)
        n_recovered = sum(r.recovered for r in rows)
        n_deferred = sum(r.outcome == "deferred_to_human_review" for r in rows)
        n_not_recovered = sum(r.outcome == "not_recovered" for r in rows)
        total_attempts = sum(r.attempt_count for r in rows)
        recovered_amount = sum(r.amount_paise for r in rows if r.recovered)
        print(
            f"{arm:>12}: recovered={n_recovered/n:.3%}  deferred={n_deferred/n:.3%}  "
            f"not_recovered={n_not_recovered/n:.3%}  attempts={total_attempts}  "
            f"recovered_amount={_fmt_paise(recovered_amount)}"
        )

    print(f"--- {label}: paired bootstrap lift (95% CI, 2000 resamples) ---")
    for arm_a, arm_b in (("rules_only", "control"), ("blind_retry", "control"), ("blind_retry", "rules_only")):
        lift = paired_bootstrap_lift(results[arm_a], results[arm_b], seed=7)
        print(
            f"  {arm_a} vs {arm_b}: rate_lift={lift.rate_lift:+.4f} "
            f"[{lift.rate_lift_ci_low:+.4f},{lift.rate_lift_ci_high:+.4f}]  "
            f"amount_lift={_fmt_paise(lift.amount_lift_paise)} "
            f"[{_fmt_paise(lift.amount_lift_ci_low_paise)},{_fmt_paise(lift.amount_lift_ci_high_paise)}]  "
            f"CI_width={lift.rate_lift_ci_high - lift.rate_lift_ci_low:.4f}"
        )

    penalty_paise = break_even_penalty_paise(results["rules_only"], results["blind_retry"], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    penalty_usd = (penalty_paise / 100) / USD_TO_INR
    print(f"--- {label}: compliance break-even ---")
    print(f"  net_value(blind_retry)={_fmt_paise(net_value_paise(results['blind_retry'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"  net_value(rules_only) ={_fmt_paise(net_value_paise(results['rules_only'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"  violations(blind_retry)={total_violations(results['blind_retry'])}")
    print(f"  break_even_penalty={_fmt_paise(penalty_paise)}  (${penalty_usd:.2f})")
    print()


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=N, seed=SEED, batch_simulated_start_at=start)

    print("=== MANIFEST -- Day 3 headline CRN recheck (does NOT replace Day 3's committed run) ===")
    print(f"git_sha     = {manifest.git_sha()}")
    print(f"corpus_hash = {manifest.corpus_hash(corpus)}")
    print(f"db_path     = {manifest.db_path()}")
    print(f"n={N}  seed={SEED}  (same corpus params as scripts/run_day3_ablation.py)")
    print()

    results_crn = _run_all_arms(corpus, use_common_random_numbers=True)
    _print_headline("CRN (fixed, real)", results_crn)

    results_old = _run_all_arms(corpus, use_common_random_numbers=False)
    _print_headline("pre-fix (comparison ONLY -- not a reportable result)", results_old)


if __name__ == "__main__":
    main()
