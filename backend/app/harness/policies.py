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
