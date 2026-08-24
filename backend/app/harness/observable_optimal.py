"""observable_optimal: the second of Day 4's two analysis bounds (see
app/harness/oracle.py for the first). Like the oracle, this is NOT a submittable
policy and NOT evaluated as a candidate to ship -- it exists to decompose the oracle
gap into two pieces with distinct meanings:

    rules_only -> observable_optimal  = value our policy leaves on the table using
                                         information it ALREADY HAS at decision time
    observable_optimal -> oracle      = value of information no real system has
                                         (the irreducible gap)

ObservableOptimalPolicy uses ONLY features a real production system has at decision
time -- decline_class, ticket size (case.amount), attempt number (len(history)+1),
card_attempts_in_window, and time since failure (now - case.simulated_at). It imports
NOTHING from app.simulator (confirmed: no import-boundary exemption needed, unlike
oracle.py -- this class could in principle be wired up as a real Policy; it's kept out
of app.harness.policies and never used as a ship candidate purely as a labeling/scope
discipline, matching the oracle's own framing, not because it structurally cheats).

Its parameters (base weight per class, a ticket-size bonus, a per-attempt penalty, a
per-day staleness penalty, a scarcity threshold, and a global cutoff) are fit by
deterministic grid search against PROPOSAL_SEED=42 -- same objective as
app.model.grid_search (net_value_paise), same "don't touch a held-out seed while
fitting" discipline. This is a genuine, if deliberately bounded, search over the full
listed observable feature set -- not exhaustive (a coarser grid on the three new
levers than the original three), documented as such below, not implied to be the
global optimum over every possible observable-feature policy.

Explicitly NOT changing app.model.playbook_schema.PlaybookProposal or any Day 4
provider/bake-off code to chase this bound -- that schema is frozen (the providers are
built against it, the abstention rule is pre-registered against it); this is analysis
that sits beside the arms already built, not a redesign of them.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import datetime, timezone

from ..corpus_builder import build_corpus
from ..gate import ActionProposal
from .compliance import net_value_paise
from .policies import ObservableCase
from .run import run_arm

# Same corpus PROPOSAL_SEED points to everywhere else in Day 4 -- see
# app.model.grid_search.CORPUS_N/CORPUS_START and app.model.seeds.PROPOSAL_SEED.
PROPOSAL_SEED = 42
CORPUS_N = 1200
CORPUS_START = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Same reference the corpus's own ticket-size distribution uses by default (see
# docs/assumptions.md's ticket_size_lognormal_median_paise) -- normalizes the ticket
# size bonus onto a scale comparable to the O(1) class weights, not a fitted constant.
TICKET_SIZE_REFERENCE_PAISE = 80_000

# Original three levers -- identical grid to app.model.grid_search, so any
# improvement found here beyond that search's own winner is attributable to the
# THREE NEW levers below, not to a finer search over the original three.
WEIGHT_RATIO_GRID: tuple[float, ...] = (0.33, 0.5, 1.0, 2.0, 3.0)
SCARCITY_THRESHOLD_GRID: tuple[int, ...] = (0, 1, 2)
DEFER_CUTOFF_GRID: tuple[float, ...] = (0.4, 0.7, 1.0, 1.5, 2.5)

# Three new levers over the observable-only feature set, deliberately coarse
# (off / one nonzero point) to keep the combined grid tractable
# (75 x 8 = 600 points, each a full run_arm at n=1200) -- a genuine but BOUNDED
# search, not exhaustive. Widening this grid is legitimate future work, not done here.
TICKET_SIZE_BONUS_GRID: tuple[float, ...] = (0.0, 0.5)
ATTEMPT_PENALTY_GRID: tuple[float, ...] = (0.0, 0.3)
STALENESS_PENALTY_PER_DAY_GRID: tuple[float, ...] = (0.0, 0.05)


@dataclass(frozen=True)
class ObservableOptimalParams:
    weight_ratio: float  # soft weight / technical weight (technical fixed at 1.0)
    scarcity_threshold: int
    defer_cutoff: float
    ticket_size_bonus: float
    attempt_penalty: float
    staleness_penalty_per_day: float


class ObservableOptimalPolicy:
    """Conforms to the exact Policy protocol shape -- runs through the unmodified
    app.harness.run.run_arm/run_ablation with zero special-casing, same as every
    other arm. Reads only case/history/now/card_attempts_in_window, all legitimately
    observable at decision time; never touches app.simulator."""

    name = "observable_optimal"

    def __init__(self, params: ObservableOptimalParams):
        self.params = params

    def _weight_for(self, decline_class: str) -> float:
        if decline_class == "soft":
            return self.params.weight_ratio
        if decline_class == "technical":
            return 1.0
        return 1.0  # 'hard' never reaches here in practice -- the gate stops it regardless

    def propose(
        self, case: ObservableCase, history: list, now: datetime, card_attempts_in_window: int,
    ) -> ActionProposal:
        # NETWORK_ATTEMPT_BUDGET_PER_CARD_30D is a real, observable, published policy
        # constant (not a simulator secret) -- same import every other scarcity-aware
        # policy in this project uses (see app.harness.policies.ModelPlaybookPolicy).
        from ..policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D

        remaining = NETWORK_ATTEMPT_BUDGET_PER_CARD_30D - card_attempts_in_window
        if remaining <= self.params.scarcity_threshold:
            attempt_number = len(history) + 1
            time_since_failure_days = (now - case.simulated_at).total_seconds() / 86_400
            score = (
                self._weight_for(case.decline_class)
                + self.params.ticket_size_bonus * (case.amount / TICKET_SIZE_REFERENCE_PAISE)
                - self.params.attempt_penalty * (attempt_number - 1)
                - self.params.staleness_penalty_per_day * time_since_failure_days
            )
            if score < self.params.defer_cutoff:
                return ActionProposal(action_type="yield_scarce_budget")
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)


def run_observable_optimal_search(corpus=None) -> tuple[ObservableOptimalParams, float]:
    """Grid search over the combined space (600 points), scored by net_value_paise
    against PROPOSAL_SEED's corpus -- returns the winning params and their net value.
    Never touches a HELD_OUT_SEED (see app.model.seeds) while fitting."""
    if corpus is None:
        corpus = build_corpus(n=CORPUS_N, seed=PROPOSAL_SEED, batch_simulated_start_at=CORPUS_START)

    from ..policy_params import COST_PER_CONTACT_ATTEMPT_MILLI_PAISE

    best_params: ObservableOptimalParams | None = None
    best_nv = float("-inf")
    for weight_ratio, scarcity_threshold, defer_cutoff, ticket_bonus, attempt_pen, staleness_pen in itertools.product(
        WEIGHT_RATIO_GRID, SCARCITY_THRESHOLD_GRID, DEFER_CUTOFF_GRID,
        TICKET_SIZE_BONUS_GRID, ATTEMPT_PENALTY_GRID, STALENESS_PENALTY_PER_DAY_GRID,
    ):
        params = ObservableOptimalParams(
            weight_ratio=weight_ratio, scarcity_threshold=scarcity_threshold, defer_cutoff=defer_cutoff,
            ticket_size_bonus=ticket_bonus, attempt_penalty=attempt_pen, staleness_penalty_per_day=staleness_pen,
        )
        rows = run_arm(
            corpus, ObservableOptimalPolicy(params), master_seed=PROPOSAL_SEED,
            retry_delay_hours=24, max_case_lifetime_days=45,
        )
        nv = net_value_paise(rows, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE)
        if nv > best_nv:
            best_nv = nv
            best_params = params

    assert best_params is not None
    return best_params, best_nv
