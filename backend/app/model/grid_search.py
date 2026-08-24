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

Traced finding from the real run (see docs/results.md): the winner sits at
scarcity_remaining_budget_threshold=0, which only ever triggers a yield at
card_attempts_in_window >= NETWORK_ATTEMPT_BUDGET_PER_CARD_30D -- the exact same
boundary at which app.gate's own network_attempt_budget_exhausted guardrail would
already reject that same proposal. At that point yielding and getting gate-rejected
are the same real-world outcome for the yielding case (no attempt, case gives up
either way) -- so the grid search is reporting that voluntary EARLIER forfeiture
(threshold=1 or 2, yielding before the gate would have anyway) never beat this
functional no-op across the swept weight ratios and cutoffs. That is the
pre-registered "allocation under contention does not pay under this outcome model"
finding, not a bug: a case's own attempt has real, immediate expected value
(SIM_TRUE_RECOVERY_RATE_BPS), while the hoped-for benefit to some other, unspecified
future case competing for the same card is diffuse and apparently doesn't outweigh it
here. (A small residual net-value gap from rules_only at this boundary-only point is
attributable to app.simulator.outcomes.attempt_succeeds's per-(arm, attempt_number)
independent seeding -- a documented, pre-existing Day 3 design choice, not something
Day 4 introduced -- not to the yield mechanism doing real work at these parameters.)
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone

from ..corpus_builder import build_corpus
from ..harness.compliance import net_value_paise
from ..harness.policies import ModelPlaybookPolicy
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


def run_grid_search(corpus=None) -> tuple[Playbook, list[GridPoint]]:
    """Runs the full grid against PROPOSAL_SEED's corpus, returns the winning Playbook
    (objective: max net_value_paise, tie-break: max recovery rate) plus every point
    scored, for transparency in docs/results.md. corpus is an injectable parameter
    only for tests -- production callers always score against the real,
    PROPOSAL_SEED-derived corpus built here."""
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


def main() -> None:
    import json
    from pathlib import Path

    winner, points = run_grid_search()
    print(f"=== grid search: {len(points)} points, PROPOSAL_SEED={PROPOSAL_SEED} ===")
    print(
        f"winner: weight_ratio={winner.rules[0].priority_weight} "
        f"scarcity_threshold={winner.scarcity_remaining_budget_threshold} "
        f"defer_cutoff={winner.defer_priority_cutoff}"
    )
    best_point = max(points, key=lambda p: (p.net_value_paise, p.recovery_rate))
    print(f"best net_value_paise = {best_point.net_value_paise:,.2f}  recovery_rate = {best_point.recovery_rate:.3%}")
    if best_point.scarcity_threshold == 0:
        print(
            "NOTE: winner selects scarcity_remaining_budget_threshold=0 -- a yield "
            "only ever fires at the exact boundary where app.gate's own "
            "network_attempt_budget_exhausted guardrail would already reject the "
            "same proposal, so voluntary EARLIER forfeiture never beat this "
            "functional no-op. Per the pre-registered statement (docs/results.md), "
            "this means allocation-under-contention does not pay under this outcome "
            "model. Reported as a finding, not softened."
        )

    out_path = Path(__file__).resolve().parent.parent.parent / "data" / "playbook_tuned_weights.json"
    out_path.write_text(winner.model_dump_json(indent=2) + "\n")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
