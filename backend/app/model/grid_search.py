"""Amendment 1's deterministic baseline: brute-force search over the exact same
Playbook parameter space a synthesized playbook fills in (per-class priority_weight,
scarcity_remaining_budget_threshold, defer_priority_cutoff), scored on real net value
against the same PROPOSAL_SEED=42 corpus docs/results.md's headline run and the
synthesis prompt both draw on. Zero network dependency -- runs the real harness
(app.harness.run.run_arm) locally, same policy code path (ModelPlaybookPolicy) and
same gate every model-sourced arm uses, so a result is attributable to the *numbers*,
not a different mechanism.

Pre-registered framing (docs/results.md, written before any provider is called): grid
search optimizes this exact objective directly against this exact data; a synthesized
playbook only ever sees aggregate summary statistics of the same data. So
model < grid_search is the expected default outcome, model ~= grid_search is the
notable one, and model > grid_search needs a real explanation -- most plausibly better
generalization on the held-out seeds, which is what the multi-seed evaluation
(app.model.seeds.HELD_OUT_SEEDS) is positioned to actually detect.

This module intentionally does NOT run on any held-out seed -- that would leak
held-out data into the same selection process being evaluated against it. It only ever
touches PROPOSAL_SEED.

SUPERSEDED FINDING, kept here as the worked example rather than scrubbed (see
docs/results.md's "Common random numbers" section for the full account): the first
run of this module found a winner at scarcity_remaining_budget_threshold=0 and
attributed its residual net-value gap over rules_only to "per-(arm, attempt_number)
independent seeding -- a documented, pre-existing Day 3 design choice." That framing
was wrong -- it was a measurement bug (app.simulator.outcomes.attempt_succeeds keyed
its RNG on arm, breaking common random numbers), not an accepted design choice, and it
meant every one of these 75 candidates was compared to rules_only, and to some extent
to each other, on noise-inflated numbers. The bug is now fixed
(use_common_random_numbers=True is run_arm's default); this module always scores
against the corrected harness now. docs/results.md's Day 4 section reports the
old-vs-new comparison (old winner, new winner, and the net-value spread across all 75
candidates under each) explicitly, so the invalidation and the correction are both on
the record, not just the correction.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone

from ..corpus_builder import build_corpus
from ..harness.compliance import net_value_paise
from ..harness.policies import ModelPlaybookPolicy, RulesOnlyPolicy
from ..harness.run import run_arm
from ..policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE
from .playbook_schema import AllocationRule, Playbook
from .seeds import PROPOSAL_SEED

# Matches docs/results.md's committed headline run (n=1201 including the one real
# harvested row -- see app.corpus_builder) so grid search scores against the exact
# data the synthesis prompt is built from.
CORPUS_N = 1200
CORPUS_START = datetime(2026, 1, 1, tzinfo=timezone.utc)

# ~5 x 3 x 5 = 75 combinations -- "a ten-line grid search," not a hyperparameter sweep.
# technical is fixed at 1.0; only the soft/technical RATIO varies, per Amendment 1's
# scoping decision (docs) not to widen the rule key beyond decline_class this pass.
WEIGHT_RATIO_GRID: tuple[float, ...] = (0.33, 0.5, 1.0, 2.0, 3.0)
SCARCITY_THRESHOLD_GRID: tuple[int, ...] = (0, 1, 2)
DEFER_CUTOFF_GRID: tuple[float, ...] = (0.4, 0.7, 1.0, 1.5, 2.5)


@dataclass(frozen=True)
class GridPoint:
    weight_ratio: float  # soft weight / technical weight (technical fixed at 1.0)
    scarcity_threshold: int
    defer_cutoff: float
    net_value_paise: float
    recovery_rate: float


def _candidate_playbook(weight_ratio: float, scarcity_threshold: int, defer_cutoff: float) -> Playbook:
    return Playbook(
        version="grid-search-candidate",
        synthesized_from_seed=PROPOSAL_SEED,
        provider="grid_search",
        model_id="deterministic",
        rules=[
            AllocationRule(
                decline_class="soft", priority_weight=weight_ratio,
                rationale="grid search candidate -- ratio to technical's fixed weight of 1.0",
            ),
            AllocationRule(
                decline_class="technical", priority_weight=1.0,
                rationale="grid search candidate -- fixed reference weight",
            ),
        ],
        scarcity_remaining_budget_threshold=scarcity_threshold,
        defer_priority_cutoff=defer_cutoff,
        abstained=False,
    )


def run_grid_search(corpus=None, use_common_random_numbers: bool = True) -> tuple[Playbook, list[GridPoint]]:
    """Runs the full grid against PROPOSAL_SEED's corpus, returns the winning Playbook
    (objective: max net_value_paise, tie-break: max recovery rate) plus every point
    scored, for transparency in docs/results.md. corpus is an injectable parameter
    only for tests -- production callers always score against the real,
    PROPOSAL_SEED-derived corpus built here.

    use_common_random_numbers=False reproduces the exact pre-fix behavior (arm-keyed
    attempt outcomes) -- kept callable only so main() can print the old-vs-new
    comparison docs/results.md reports; never use False for a result that ships."""
    if corpus is None:
        corpus = build_corpus(n=CORPUS_N, seed=PROPOSAL_SEED, batch_simulated_start_at=CORPUS_START)

    points: list[GridPoint] = []
    for weight_ratio, scarcity_threshold, defer_cutoff in itertools.product(
        WEIGHT_RATIO_GRID, SCARCITY_THRESHOLD_GRID, DEFER_CUTOFF_GRID,
    ):
        candidate = _candidate_playbook(weight_ratio, scarcity_threshold, defer_cutoff)
        rows = run_arm(
            corpus, ModelPlaybookPolicy(candidate, name="grid_search_probe"),
            master_seed=PROPOSAL_SEED, retry_delay_hours=24, max_case_lifetime_days=45,
            use_common_random_numbers=use_common_random_numbers,
        )
        nv = net_value_paise(rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
        rate = sum(r.recovered for r in rows) / len(rows)
        points.append(GridPoint(weight_ratio, scarcity_threshold, defer_cutoff, nv, rate))

    best = max(points, key=lambda p: (p.net_value_paise, p.recovery_rate))
    winner = Playbook(
        version="tuned_weights-v1",
        synthesized_from_seed=PROPOSAL_SEED,
        provider="grid_search",
        model_id="deterministic",
        rules=[
            AllocationRule(
                decline_class="soft", priority_weight=best.weight_ratio,
                rationale=(
                    f"deterministic grid search over {len(points)} points against the "
                    f"PROPOSAL_SEED={PROPOSAL_SEED} corpus; maximizes net value "
                    f"(tie-break: recovery rate)"
                ),
            ),
            AllocationRule(
                decline_class="technical", priority_weight=1.0,
                rationale="fixed reference weight -- only the soft/technical ratio was searched",
            ),
        ],
        scarcity_remaining_budget_threshold=best.scarcity_threshold,
        defer_priority_cutoff=best.defer_cutoff,
        abstained=False,
    )
    return winner, points


def _spread(points: list[GridPoint]) -> tuple[float, float, float]:
    values = [p.net_value_paise for p in points]
    return min(values), max(values), (max(values) - min(values))


def main() -> None:
    import statistics
    from pathlib import Path

    corpus = build_corpus(n=CORPUS_N, seed=PROPOSAL_SEED, batch_simulated_start_at=CORPUS_START)
    rules_only_rows = run_arm(
        corpus, RulesOnlyPolicy(), master_seed=PROPOSAL_SEED,
        retry_delay_hours=24, max_case_lifetime_days=45,
    )
    rules_only_nv = net_value_paise(rules_only_rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
    rules_only_rate = sum(r.recovered for r in rules_only_rows) / len(rules_only_rows)

    print(f"=== grid search under COMMON RANDOM NUMBERS (fixed, real), PROPOSAL_SEED={PROPOSAL_SEED} ===")
    winner_new, points_new = run_grid_search(corpus=corpus, use_common_random_numbers=True)
    best_new = max(points_new, key=lambda p: (p.net_value_paise, p.recovery_rate))
    lo_new, hi_new, spread_new = _spread(points_new)
    print(
        f"winner: weight_ratio={winner_new.rules[0].priority_weight} "
        f"scarcity_threshold={winner_new.scarcity_remaining_budget_threshold} "
        f"defer_cutoff={winner_new.defer_priority_cutoff}"
    )
    print(f"best net_value_paise = {best_new.net_value_paise:,.2f}  recovery_rate = {best_new.recovery_rate:.3%}")
    print(f"rules_only (same corpus/seed, CRN):    net_value_paise = {rules_only_nv:,.2f}  recovery_rate = {rules_only_rate:.3%}")
    print(f"75-point net_value spread: [{lo_new:,.2f}, {hi_new:,.2f}]  width={spread_new:,.2f}")

    print(f"\n=== grid search WITHOUT common random numbers (pre-fix, for comparison ONLY -- not shipped) ===")
    winner_old, points_old = run_grid_search(corpus=corpus, use_common_random_numbers=False)
    best_old = max(points_old, key=lambda p: (p.net_value_paise, p.recovery_rate))
    lo_old, hi_old, spread_old = _spread(points_old)
    print(
        f"winner: weight_ratio={winner_old.rules[0].priority_weight} "
        f"scarcity_threshold={winner_old.scarcity_remaining_budget_threshold} "
        f"defer_cutoff={winner_old.defer_priority_cutoff}"
    )
    print(f"best net_value_paise = {best_old.net_value_paise:,.2f}  recovery_rate = {best_old.recovery_rate:.3%}")
    print(f"75-point net_value spread: [{lo_old:,.2f}, {hi_old:,.2f}]  width={spread_old:,.2f}")

    same_winner = (
        winner_new.rules[0].priority_weight == winner_old.rules[0].priority_weight
        and winner_new.scarcity_remaining_budget_threshold == winner_old.scarcity_remaining_budget_threshold
        and winner_new.defer_priority_cutoff == winner_old.defer_priority_cutoff
    )
    print(f"\nsame winner under both? {same_winner}")
    print(
        f"noise share of the pre-fix 75-point spread: this fixed run's spread "
        f"({spread_new:,.2f}) vs the old run's spread ({spread_old:,.2f}) -- "
        f"{'the pre-fix spread was WIDER, consistent with the old run partly selecting on noise' if spread_old > spread_new else 'the pre-fix spread was not wider than the fixed run -- report exactly as observed'}"
    )

    if best_new.scarcity_threshold == 0:
        print(
            "\nNOTE: the CRN winner selects scarcity_remaining_budget_threshold=0 -- a "
            "yield only ever fires at the exact boundary where app.gate's own "
            "network_attempt_budget_exhausted guardrail would already reject the "
            "same proposal, so voluntary EARLIER forfeiture never beat this "
            "functional no-op. Per the pre-registered statement (docs/results.md), "
            "this means allocation-under-contention does not pay under this outcome "
            "model. Reported as a finding, not softened -- and this CRN run is what "
            "the finding is now adjudicated against; the pre-fix run is superseded."
        )

    out_path = Path(__file__).resolve().parent.parent.parent / "data" / "playbook_tuned_weights.json"
    out_path.write_text(winner_new.model_dump_json(indent=2) + "\n")
    print(f"\nwrote {out_path} (CRN winner)")


if __name__ == "__main__":
    main()
