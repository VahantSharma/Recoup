"""The case state machine's legal transitions, and idempotency key derivation.

Every transition is a row update — nothing skips straight from ELIGIBLE to ACTED. A
process that dies between RECONCILING and ACTED resumes by re-reading the case's
`state` and the case_attempts row's `idempotency_key`, not by re-deriving intent from
scratch.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "INTAKE": {"CLASSIFIED"},
    "CLASSIFIED": {"EXCLUDED", "ELIGIBLE"},
    "ELIGIBLE": {"PROPOSED"},
    "PROPOSED": {"GATE_APPROVED", "GATE_REJECTED"},
    "GATE_APPROVED": {"SCHEDULED"},
    "GATE_REJECTED": {"NEEDS_REVIEW", "NOT_WORKED"},
    "SCHEDULED": {"RECONCILING"},
    "RECONCILING": {"ACTING"},
    "ACTING": {"ACTED"},
    "ACTED": {"RECOVERED", "STILL_FAILED"},
    "STILL_FAILED": {"SCHEDULED", "DONE"},  # SCHEDULED = next attempt, if under budget
    "RECOVERED": {"DONE"},
    "EXCLUDED": set(),
    "NOT_WORKED": set(),
    "NEEDS_REVIEW": set(),  # human resolves out of band — out of scope for Day 1
    "DONE": set(),
}

TERMINAL_STATES = frozenset(state for state, nxt in LEGAL_TRANSITIONS.items() if not nxt)
ALL_STATES = frozenset(LEGAL_TRANSITIONS)


class IllegalTransition(ValueError):
    """Raised when a requested state change isn't in LEGAL_TRANSITIONS."""


class _HasState(Protocol):
    state: str
    state_updated_at: datetime


def transition(case: _HasState, new_state: str, *, now: Callable[[], datetime]) -> None:
    """Move `case` to `new_state` if legal; raise IllegalTransition otherwise.

    `now` is injected (not datetime.now() called directly) so tests can assert on an
    exact timestamp instead of a fuzzy "sometime around when the test ran."
    """
    allowed = LEGAL_TRANSITIONS.get(case.state, set())
    if new_state not in allowed:
        raise IllegalTransition(f"{case.state!r} -> {new_state!r} is not a legal transition")
    case.state = new_state
    case.state_updated_at = now()


def derive_idempotency_key(case_id: str, attempt_number: int) -> str:
    """Deterministic per (case_id, attempt_number): a replayed attempt derives the same
    key, and case_attempts.idempotency_key's UNIQUE constraint turns that into a no-op
    instead of a second money-touching call. This is *our* enforcement, not Razorpay's —
    Razorpay's idempotency headers (X-Payout/Refund/Transfer-Idempotency) don't cover
    the Orders/Payment Links endpoints a retry actually uses.
    """
    return hashlib.sha256(f"{case_id}:{attempt_number}".encode("utf-8")).hexdigest()
