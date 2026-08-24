"""The playbook: a small, versioned, committed rule set synthesized once (from real
Day 3 run data, or by deterministic grid search) and applied by a pure-Python policy
with zero network calls at evaluation time. Not a per-case decision log (wouldn't
generalize to a held-out seed) and not free text (needs to be applied
deterministically) -- see docs/buildathon-plan.md's Day 4 section.

What this schema does NOT let a playbook express: nothing here can say "retry a hard
decline," "skip reconciliation," or "exceed the ceiling" -- the schema's own shape is
one more layer keeping the model's (or the grid search's) output space inside what
app.gate already forecloses. ModelPlaybookPolicy (app/harness/policies.py) reads a
Playbook to decide, for a gate-permitted retry, (a) a relative priority_weight and (b)
whether to voluntarily yield a scarce card slot instead of acting -- it never gets a
vote on whether an action is permitted at all. That's still app.gate.evaluate(),
unchanged.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AllocationRule(BaseModel):
    # 'hard' never appears -- by taxonomy, a hard decline is never retried, so it has
    # no allocation weight to assign. None = applies to both remaining classes.
    decline_class: Literal["soft", "technical"] | None
    priority_weight: float = Field(gt=0)
    rationale: str = Field(min_length=1, max_length=280)


class Playbook(BaseModel):
    version: str
    synthesized_from_seed: int
    provider: str  # "gemini" | "groq" | "grid_search" | "placeholder"
    model_id: str
    rules: list[AllocationRule]

    # Yield-at-scarcity: when a card's remaining rolling-30-day attempt budget drops to
    # or below this, a case whose own class weight is below defer_priority_cutoff
    # voluntarily yields its attempt this round rather than competing for the scarce
    # slot -- see app.harness.policies.ModelPlaybookPolicy. Yielding is TERMINAL for
    # the yielding case (app.harness.run.state.give_up() never schedules another
    # attempt) -- this is a permanent forfeiture of that case's remaining recovery
    # probability, not a "try again later." Named honestly for that reason: nothing
    # downstream should ever call this "deferral."
    scarcity_remaining_budget_threshold: int = Field(ge=0)
    defer_priority_cutoff: float = Field(gt=0)

    abstained: bool
    abstain_reason: str | None = None  # populated iff abstained

    def weight_for(self, decline_class: str) -> float:
        """The priority_weight that applies to a case of this decline_class -- an
        exact-class rule wins over the None (applies-to-both) rule; falls back to 1.0
        (neutral -- behaves like RulesOnlyPolicy for this class) if neither is
        present, which should only happen for a malformed/incomplete playbook."""
        exact = next((r for r in self.rules if r.decline_class == decline_class), None)
        if exact is not None:
            return exact.priority_weight
        wildcard = next((r for r in self.rules if r.decline_class is None), None)
        if wildcard is not None:
            return wildcard.priority_weight
        return 1.0
