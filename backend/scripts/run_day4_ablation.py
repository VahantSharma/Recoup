"""Day 4 held-out ablation, final form: six submittable/candidate arms (control,
blind_retry, rules_only, tuned_weights, rules_plus_model_gemini,
rules_plus_model_groq) plus two analysis-only reference rows
(observable_optimal, oracle_upper_bound -- never candidates, see
app/harness/observable_optimal.py and app/harness/oracle.py's own docstrings), all
across the 10 HELD_OUT_SEEDS (app.model.seeds), none seen at grid-search or synthesis
time (PROPOSAL_SEED=42).

Amendment 2: a single held-out point captures within-corpus variance only, not
corpus-to-corpus variance -- this script reports the distribution of each
model-sourced arm's lift over rules_only across all 10 seeds, and how often the full
ranking holds.

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
from app.export import build_manifest, write_artifact
from app.export_schemas import ArmHeldOutRow, Day4HeldOutAblationArtifact, LiftDistribution
from app.harness.compliance import total_violations
from app.harness.observable_optimal import ObservableOptimalParams, ObservableOptimalPolicy
from app.harness.oracle import OracleUpperBoundPolicy
from app.harness.policies import BlindRetryPolicy, ControlPolicy, ModelPlaybookPolicy, RulesOnlyPolicy
from app.harness.run import run_arm
from app.harness.stats import paired_bootstrap_lift
from app.model.playbook_schema import Playbook
from app.model.seeds import HELD_OUT_SEEDS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
N = 1200
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45
USE_COMMON_RANDOM_NUMBERS = True

TUNED_WEIGHTS_FILE = "playbook_tuned_weights.json"
RULES_PLUS_MODEL_GEMINI_FILE = "playbook_gemini_v1.json"
RULES_PLUS_MODEL_GROQ_FILE = "playbook_groq_v1.json"

SUBMITTABLE_ARMS = (
    "control", "blind_retry", "rules_only", "tuned_weights",
    "rules_plus_model_gemini", "rules_plus_model_groq",
)
REFERENCE_ARMS = ("observable_optimal", "oracle_upper_bound")
ALL_ARMS = SUBMITTABLE_ARMS + REFERENCE_ARMS
MODEL_SOURCED_ARMS = ("tuned_weights", "rules_plus_model_gemini", "rules_plus_model_groq")


def _load_playbook(filename: str) -> Playbook:
    return Playbook(**json.loads((DATA_DIR / filename).read_text()))


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _run_all_arms(seed: int, oo_params: ObservableOptimalParams) -> dict[str, list]:
    corpus = build_corpus(n=N, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    tuned_weights_pb = _load_playbook(TUNED_WEIGHTS_FILE)
    gemini_pb = _load_playbook(RULES_PLUS_MODEL_GEMINI_FILE)
    groq_pb = _load_playbook(RULES_PLUS_MODEL_GROQ_FILE)

    policies = {
        "control": ControlPolicy(),
        "blind_retry": BlindRetryPolicy(),
        "rules_only": RulesOnlyPolicy(),
        "tuned_weights": ModelPlaybookPolicy(tuned_weights_pb, name="tuned_weights"),
        "rules_plus_model_gemini": ModelPlaybookPolicy(gemini_pb, name="rules_plus_model_gemini"),
        "rules_plus_model_groq": ModelPlaybookPolicy(groq_pb, name="rules_plus_model_groq"),
        "observable_optimal": ObservableOptimalPolicy(oo_params),
        "oracle_upper_bound": OracleUpperBoundPolicy(master_seed=seed, max_case_lifetime_days=MAX_CASE_LIFETIME_DAYS),
    }
    return {
        name: run_arm(
            corpus, policy, seed, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS,
            use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS,
        )
        for name, policy in policies.items()
    }


def _rate(rows) -> float:
    return sum(r.recovered for r in rows) / len(rows)


def main() -> None:
    from app.harness.observable_optimal import run_observable_optimal_search

    print("=== MANIFEST -- Day 4 held-out ablation (final: 6 submittable + 2 reference arms) ===")
    print(f"git_sha            = {manifest.git_sha()}")
    print(f"db_path            = {manifest.db_path()}")
    print(f"held_out_seeds     = {list(HELD_OUT_SEEDS)}")
    print(f"n per seed         = {N}")
    print(f"use_common_random_numbers = {USE_COMMON_RANDOM_NUMBERS}")
    missing = [f for f in (TUNED_WEIGHTS_FILE, RULES_PLUS_MODEL_GEMINI_FILE, RULES_PLUS_MODEL_GROQ_FILE) if not (DATA_DIR / f).exists()]
    if missing:
        raise SystemExit(f"missing playbook file(s): {missing} -- run grid_search / synthesize_playbook first")
    print()

    print("--- re-deriving observable_optimal's fitted params (deterministic, zero network) ---")
    oo_params, _ = run_observable_optimal_search()
    print(f"observable_optimal params: {oo_params}")
    print()

    per_seed_results: dict[int, dict[str, list]] = {
        seed: _run_all_arms(seed, oo_params) for seed in HELD_OUT_SEEDS
    }

    print("--- per-seed lift: each model-sourced/reference arm vs rules_only (rate lift, 95% CI) ---")
    rate_deltas: dict[str, list[float]] = {arm: [] for arm in MODEL_SOURCED_ARMS + REFERENCE_ARMS}
    yield_counts: dict[str, list[int]] = {arm: [] for arm in MODEL_SOURCED_ARMS}
    for seed in HELD_OUT_SEEDS:
        results = per_seed_results[seed]
        line = [f"seed={seed}:"]
        for arm in MODEL_SOURCED_ARMS + REFERENCE_ARMS:
            lift = paired_bootstrap_lift(results[arm], results["rules_only"], seed=7)
            rate_deltas[arm].append(lift.rate_lift)
            line.append(f"{arm}-rules_only={lift.rate_lift:+.4f}[{lift.rate_lift_ci_low:+.4f},{lift.rate_lift_ci_high:+.4f}]")
        for arm in MODEL_SOURCED_ARMS:
            yield_counts[arm].append(sum(r.final_status == "gave_up_yielded_scarce_budget" for r in results[arm]))
        print("  " + "  ".join(line))

    def _summary(name: str, deltas: list[float]) -> None:
        print(f"\n{name} distribution across {len(deltas)} held-out seeds:")
        print(f"  mean={statistics.mean(deltas):+.4f}  stdev={statistics.pstdev(deltas):.4f}  min={min(deltas):+.4f}  max={max(deltas):+.4f}")
        print(f"  positive (beats rules_only) in {sum(d > 0 for d in deltas)}/{len(deltas)} seeds")

    for arm in MODEL_SOURCED_ARMS + REFERENCE_ARMS:
        _summary(f"{arm} - rules_only rate lift", rate_deltas[arm])
    print(f"\ntotal yields across all seeds: " + "  ".join(f"{arm}={sum(yield_counts[arm])}" for arm in MODEL_SOURCED_ARMS))

    print(f"\n--- full ranking (by absolute recovery rate, descending), per held-out seed, all {len(ALL_ARMS)} arms ---")
    rankings = []
    for seed in HELD_OUT_SEEDS:
        results = per_seed_results[seed]
        rates = {arm: _rate(results[arm]) for arm in ALL_ARMS}
        ranking = tuple(sorted(ALL_ARMS, key=lambda a: -rates[a]))
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

    # --- Stage 3 export: all 8 arms, held-out lift distributions, violations in the
    # SAME row as gross recovery (never a separate table), shippable vs analysis-only
    # marked explicitly per docs/day5surfaceplan.md's Stage 3 instruction. ---
    SHIPPABLE = {
        "control", "blind_retry", "rules_only", "tuned_weights",
        "rules_plus_model_gemini", "rules_plus_model_groq",
    }
    arm_rows: list[ArmHeldOutRow] = []
    for arm in ALL_ARMS:
        total_arm_violations = sum(
            total_violations(per_seed_results[seed][arm]) for seed in HELD_OUT_SEEDS
        )
        mean_rate = statistics.mean(_rate(per_seed_results[seed][arm]) for seed in HELD_OUT_SEEDS)
        lift_dist = None
        if arm in rate_deltas:
            deltas = rate_deltas[arm]
            lift_dist = LiftDistribution(
                mean=statistics.mean(deltas), stdev=statistics.pstdev(deltas),
                min=min(deltas), max=max(deltas), positive_seeds=sum(d > 0 for d in deltas),
                total_seeds=len(deltas),
            )
        total_yields = sum(yield_counts[arm]) if arm in yield_counts else None
        arm_rows.append(ArmHeldOutRow(
            arm=arm, is_shippable=arm in SHIPPABLE, mean_recovery_rate=mean_rate,
            total_violations=total_arm_violations, lift_vs_rules_only=lift_dist, total_yields=total_yields,
        ))

    artifact = Day4HeldOutAblationArtifact(
        held_out_seeds=list(HELD_OUT_SEEDS), n_per_seed=N, arms=arm_rows,
        modal_ranking=list(modal_ranking), modal_ranking_hold_count=modal_count,
        per_seed_rankings=[list(r) for r in rankings],
    )
    export_manifest = build_manifest(
        script="scripts/run_day4_ablation.py", schema_name=Day4HeldOutAblationArtifact.SCHEMA_NAME,
        schema_version=Day4HeldOutAblationArtifact.SCHEMA_VERSION,
        seed={"held_out_seeds": list(HELD_OUT_SEEDS)}, corpus_hash=None,
        policy_params={}, simulator_params={}, use_common_random_numbers=USE_COMMON_RANDOM_NUMBERS,
    )
    out_path = write_artifact(
        Day4HeldOutAblationArtifact.SCHEMA_NAME, Day4HeldOutAblationArtifact.SCHEMA_VERSION, export_manifest, artifact,
    )
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
