"""What each arm proposes. Deliberately receives a closed, hand-maintained
ObservableCase — never the raw PaymentCase ORM object, which could grow a column over
time that accidentally carries simulator-derived data into a policy's view just by
existing. See tests/test_policy_input_boundary.py, which checks this structurally,
not just by convention.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..gate import ActionProposal
from ..model.playbook_schema import Playbook  # schema only -- never provider/cache/
                                                # ratelimit/gemini_provider/groq_provider.
                                                # See tests/test_no_model_calls_in_reproducible_paths.py.
from ..policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D


@dataclass(frozen=True)
class ObservableCase:
    """Everything a policy may see about a case. Mirrors the policy-relevant subset of
    app.models.PaymentCase but is hand-maintained and reviewed, not derived from it —
    field names match PaymentCase's (`amount`, not `amount_paise`) so this object can
    be passed directly to app.gate.evaluate() without an adapter."""

    id: str
    amount: int  # paise
    currency: str
    decline_class: str
    decline_class_source: str
    risk_flagged: bool
    card_id: str | None
    simulated_at: datetime
    opt_out: bool = False  # do-not-disturb -- see app.harness.run's own opt_out
        # check, which excludes a case with this set to True from ever reaching
        # Policy.propose() at all, for any arm. A policy never gets to read this
        # field itself (there's no reason to: by the time propose() could see a
        # case, opt_out has already been checked and the case has already been
        # excluded if it was set) -- present here only so ObservableCase carries the
        # same shape as the corpus row it's built from.


@dataclass(frozen=True)
class AttemptHistoryEntry:
    """An observed fact about a past attempt on this case — real information a real
    ops system would show a policy, not a leak. `outcome` is only ever populated after
    that attempt actually happened."""

    attempt_number: int
    action_type: str
    gate_decision: str
    gate_reason: str
    executed_at: datetime | None
    outcome: str | None  # "recovered" | "still_failed" | None (not yet resolved)


class Policy(Protocol):
    name: str

    def propose(
        self,
        case: ObservableCase,
        history: list[AttemptHistoryEntry],
        now: datetime,
        card_attempts_in_window: int,
    ) -> ActionProposal: ...


class ControlPolicy:
    """Always proposes no_action. Whatever it 'recovers' is, by definition, organic —
    this arm is the baseline everything else's lift is measured against."""

    name = "control"

    def propose(
        self, case: ObservableCase, history: list[AttemptHistoryEntry], now: datetime,
        card_attempts_in_window: int,
    ) -> ActionProposal:
        return ActionProposal(action_type="no_action")


class BlindRetryPolicy:
    """Always proposes a retry — the harness calls the gate in audit_only mode for
    this arm (see app.harness.run) and executes regardless of the verdict, logging a
    violation whenever the gate would have rejected. The enforcement asymmetry lives
    in the harness's dispatch, not here — propose() itself doesn't know or care
    whether it's being enforced."""

    name = "blind_retry"

    def propose(
        self, case: ObservableCase, history: list[AttemptHistoryEntry], now: datetime,
        card_attempts_in_window: int,
    ) -> ActionProposal:
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)


class ModelPlaybookPolicy:
    """Reads a Playbook (app.model.playbook_schema) to make exactly one decision a
    playbook is allowed to make: whether THIS policy voluntarily yields a scarce
    card slot right now, rather than competing for it. It never gets a vote on
    whether an action is *permitted* — proposing retry_payment_link here goes through
    app.gate.evaluate() exactly like RulesOnlyPolicy's does, unchanged.

    Same class serves every playbook-sourced arm (tuned_weights via grid search,
    rules_plus_model_gemini, rules_plus_model_groq) — only the Playbook and `name`
    differ per instance, so a positive/negative result is attributable to the
    playbook's numbers, not to a different code path."""

    def __init__(self, playbook: Playbook, name: str):
        self.playbook = playbook
        self.name = name

    def propose(
        self, case: ObservableCase, history: list[AttemptHistoryEntry], now: datetime,
        card_attempts_in_window: int,
    ) -> ActionProposal:
        if not self.playbook.abstained:
            remaining = NETWORK_ATTEMPT_BUDGET_PER_CARD_30D - card_attempts_in_window
            if remaining <= self.playbook.scarcity_remaining_budget_threshold:
                weight = self.playbook.weight_for(case.decline_class)
                if weight < self.playbook.defer_priority_cutoff:
                    # TERMINAL for this case -- see app.harness.run's handling of this
                    # action_type and docs/assumptions.md's naming note. Never
                    # proposed for a 'hard' case in practice (RulesOnlyPolicy-style
                    # retry proposals for 'hard' cases are rejected by the gate's own
                    # hard_decline_stop guardrail before this would ever matter, same
                    # as every other arm) -- this policy doesn't special-case
                    # decline_class beyond what weight_for() already does.
                    return ActionProposal(action_type="yield_scarce_budget")
        # Abstained, or not scarce, or this case's weight clears the cutoff: propose
        # the same retry every enforced arm proposes -- identical to RulesOnlyPolicy.
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)


class RulesOnlyPolicy:
    """Proposes the same retry BlindRetryPolicy does — the difference is entirely in
    enforcement (the harness calls the gate normally for this arm and only executes
    when approved), not in what's proposed. Kept as a distinct named class rather than
    reusing BlindRetryPolicy's, for legibility in code, tests, and the pitch — Day 4's
    rules_plus_model arm is where propose() logic actually starts to differ."""

    name = "rules_only"

    def propose(
        self, case: ObservableCase, history: list[AttemptHistoryEntry], now: datetime,
        card_attempts_in_window: int,
    ) -> ActionProposal:
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)
