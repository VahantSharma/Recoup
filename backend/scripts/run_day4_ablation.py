"""Day 4 held-out ablation: five policies (control, blind_retry, rules_only,
tuned_weights, rules_plus_model), ten held-out seeds (app.model.seeds.HELD_OUT_SEEDS),
none seen at grid-search or synthesis time (PROPOSAL_SEED=42).

Amendment 2: a single held-out point captures within-corpus variance only, not
corpus-to-corpus variance -- Day 3's own doctrine (docs/results.md's sensitivity
sweep) is that the RANKING, not the number, is the result, established across a swept
grid. This script applies the same discipline one level up: reports the distribution
of each model-sourced arm's lift over rules_only across all 10 seeds, and how often
the full 5-arm ranking (by absolute recovery rate) holds, naming the condition where
it flips if it does.

Placeholder-first (Amendment 5): this script currently loads
data/playbook_v0_placeholder.json for the rules_plus_model arm -- proving the whole
harness end to end with zero network dependency before step 16 swaps in the real,
synthesized winner. tuned_weights already loads the real, final
data/playbook_tuned_weights.json (step 6 -- zero network dependency either way).

Run: cd backend && python -m scripts.run_day4_ablation
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from app import manifest
from app.corpus_builder import build_corpus
from app.harness.policies import BlindRetryPolicy, ControlPolicy, ModelPlaybookPolicy, RulesOnlyPolicy
from app.harness.run import run_ablation
from app.harness.stats import paired_bootstrap_lift
from app.model.playbook_schema import Playbook
from app.model.seeds import HELD_OUT_SEEDS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
N = 1200
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45

# Swapped for the real, synthesized winner at step 16 -- see the module docstring.
RULES_PLUS_MODEL_PLAYBOOK_FILE = "playbook_v0_placeholder.json"
TUNED_WEIGHTS_PLAYBOOK_FILE = "playbook_tuned_weights.json"

# True (default, real) -- the fixed, correctly-paired harness (see
# app.simulator.outcomes.attempt_succeeds and docs/results.md's "Common random
# numbers" section). False reproduces the pre-fix behavior for comparison ONLY --
# never the source of a reported result.
USE_COMMON_RANDOM_NUMBERS = True


def _load_playbook(filename: str) -> Playbook:
    return Playbook(**json.loads((DATA_DIR / filename).read_text()))


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def build_policies() -> dict[str, object]:
    tuned_weights_pb = _load_playbook(TUNED_WEIGHTS_PLAYBOOK_FILE)
    rules_plus_model_pb = _load_playbook(RULES_PLUS_MODEL_PLAYBOOK_FILE)
    return {
        "control": ControlPolicy(),
        "blind_retry": BlindRetryPolicy(),
        "rules_only": RulesOnlyPolicy(),
        "tuned_weights": ModelPlaybookPolicy(tuned_weights_pb, name="tuned_weights"),
        "rules_plus_model": ModelPlaybookPolicy(rules_plus_model_pb, name="rules_plus_model"),
    }


def main() -> None:
    policies = build_policies()
    arm_names = list(policies.keys())
    using_placeholder = RULES_PLUS_MODEL_PLAYBOOK_FILE == "playbook_v0_placeholder.json"

    print("=== MANIFEST -- Day 4 held-out ablation ===")
    print(f"git_sha            = {manifest.git_sha()}")
    print(f"db_path            = {manifest.db_path()}")
    print(f"held_out_seeds     = {list(HELD_OUT_SEEDS)}")
    print(f"n per seed         = {N}")
    print(f"tuned_weights_file = {TUNED_WEIGHTS_PLAYBOOK_FILE}")
    print(f"rules_plus_model_file = {RULES_PLUS_MODEL_PLAYBOOK_FILE}"
          + ("  *** PLACEHOLDER -- not a reportable result until step 16 swaps the real winner in ***" if using_placeholder else ""))
    print(f"use_common_random_numbers = {USE_COMMON_RANDOM_NUMBERS}"
          + ("" if USE_COMMON_RANDOM_NUMBERS else "  *** PRE-FIX MODE -- comparison only, not a reportable result ***"))
    print()

    per_seed_results: dict[int, dict[str, list]] = {}
    for seed in HELD_OUT_SEEDS:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        corpus = build_corpus(n=N, seed=seed, batch_simulated_start_at=start)
        per_seed_results[seed] = run_ablation(
            corpus, list(policies.values()), master_seed=seed,
            retry_delay_hours=RETRY_DELAY_HOURS, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS,
            use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS,
        )

    print("--- per-seed lift: model-sourced arms vs rules_only (rate lift, 95% CI) ---")
    tw_rate_deltas: list[float] = []
    rpm_rate_deltas: list[float] = []
    tw_net_yield_counts: list[int] = []
    rpm_net_yield_counts: list[int] = []
    for seed in HELD_OUT_SEEDS:
        results = per_seed_results[seed]
        tw_lift = paired_bootstrap_lift(results["tuned_weights"], results["rules_only"], seed=7)
        rpm_lift = paired_bootstrap_lift(results["rules_plus_model"], results["rules_only"], seed=7)
        tw_rate_deltas.append(tw_lift.rate_lift)
        rpm_rate_deltas.append(rpm_lift.rate_lift)
        tw_net_yield_counts.append(sum(r.final_status == "gave_up_yielded_scarce_budget" for r in results["tuned_weights"]))
        rpm_net_yield_counts.append(sum(r.final_status == "gave_up_yielded_scarce_budget" for r in results["rules_plus_model"]))
        print(
            f"seed={seed}: tuned_weights-rules_only={tw_lift.rate_lift:+.4f} "
            f"[{tw_lift.rate_lift_ci_low:+.4f},{tw_lift.rate_lift_ci_high:+.4f}]  "
            f"rules_plus_model-rules_only={rpm_lift.rate_lift:+.4f} "
            f"[{rpm_lift.rate_lift_ci_low:+.4f},{rpm_lift.rate_lift_ci_high:+.4f}]  "
            f"yields(tw/rpm)={tw_net_yield_counts[-1]}/{rpm_net_yield_counts[-1]}"
        )

    def _summary(name: str, deltas: list[float]) -> None:
        print(f"\n{name} distribution across {len(deltas)} held-out seeds:")
        print(
            f"  mean={statistics.mean(deltas):+.4f}  stdev={statistics.pstdev(deltas):.4f}  "
            f"min={min(deltas):+.4f}  max={max(deltas):+.4f}"
        )
        print(f"  positive (beats rules_only) in {sum(d > 0 for d in deltas)}/{len(deltas)} seeds")

    _summary("tuned_weights - rules_only rate lift", tw_rate_deltas)
    _summary("rules_plus_model - rules_only rate lift", rpm_rate_deltas)
    print(f"\ntotal yields across all seeds: tuned_weights={sum(tw_net_yield_counts)}  rules_plus_model={sum(rpm_net_yield_counts)}")

    print("\n--- 5-arm ranking (by absolute recovery rate, descending), per held-out seed ---")
    rankings = []
    for seed in HELD_OUT_SEEDS:
        results = per_seed_results[seed]
        rates = {arm: sum(r.recovered for r in rows) / len(rows) for arm, rows in results.items()}
        ranking = tuple(sorted(arm_names, key=lambda a: -rates[a]))
        rankings.append(ranking)
        print(f"seed={seed}: " + " > ".join(ranking))

    counts = Counter(rankings)
    modal_ranking, modal_count = counts.most_common(1)[0]
    print(f"\nmodal ranking ({modal_count}/{len(HELD_OUT_SEEDS)} seeds): " + " > ".join(modal_ranking))
    if modal_count < len(HELD_OUT_SEEDS):
        print("ranking did NOT hold at every seed -- distinct rankings observed:")
        for ranking, count in counts.most_common():
            print(f"  {count}/{len(HELD_OUT_SEEDS)}: " + " > ".join(ranking))
    else:
        print("ranking held at every held-out seed.")


if __name__ == "__main__":
    main()
