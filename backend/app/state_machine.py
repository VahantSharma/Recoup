"""The case state machine's legal transitions, and idempotency key derivation.

Every transition is a row update — nothing skips straight from ELIGIBLE to ACTED. A
process that dies mid-action resumes by re-reading the case's `state` and the
case_attempts row's `idempotency_key`, not by re-deriving intent from scratch — see
`app.main.verify_recovery_action` for the one live path that actually exercises this,
and `docs/results.md`'s state-machine-ordering correction for why the order below is
what it is, not the order this table originally shipped with.

Corrected transition order (Day 5, found while wiring the live endpoint through every
state for real): `app.gate.evaluate()` REQUIRES `reconciled_payment`/`reconciled_at`
as arguments — it cannot be called at all without a reconcile already having happened.
The original table had RECONCILING positioned AFTER GATE_APPROVED, which is
structurally impossible given the gate's own signature — a leftover from Day 1, when
this table was designed before the gate (Day 2) existed, never re-checked against the
gate's actual requirements once it was built. RECONCILING now precedes PROPOSED: reconcile
first, THEN propose (using the fresh reconciled data the gate needs), THEN gate decides,
THEN act immediately if approved — matching how `gate.evaluate()` and the live endpoint
actually work, not an idealized sequence that was never actually callable.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime
from typing import Protocol

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "INTAKE": {"CLASSIFIED"},
    "CLASSIFIED": {"EXCLUDED", "ELIGIBLE"},
    "ELIGIBLE": {"SCHEDULED"},  # a case becomes eligible, and its first attempt is
                                  # scheduled — immediately, in the one live path today;
                                  # a future scheduler could delay this without changing
                                  # anything downstream
    "SCHEDULED": {"RECONCILING"},
    "RECONCILING": {"PROPOSED"},  # reconcile MUST happen before a proposal is built,
                                     # because gate.evaluate() requires the reconciled
                                     # result as an input — it cannot run without one
    "PROPOSED": {"GATE_APPROVED", "GATE_REJECTED", "RECONCILING"},  # the RECONCILING
                                     # re-entry is the crash-resume path: a prior process
                                     # for this same attempt got here and died before ever
                                     # writing a case_attempts row (the only irreversible
                                     # step so far), so restarting the decision fresh is
                                     # always safe — never trust reconcile data left over
                                     # from a crashed run anyway
    "GATE_APPROVED": {"ACTING", "RECONCILING"},  # act immediately in the normal path —
                                     # the reconcile that fed this decision is still
                                     # fresh, no second reconcile window opens between
                                     # approval and action. RECONCILING is the same
                                     # crash-resume re-entry as PROPOSED's, for a process
                                     # that died after approval but still before the
                                     # case_attempts row was committed
    "GATE_REJECTED": {"NEEDS_REVIEW", "NOT_WORKED", "REFUSED"},
    "ACTING": {"ACTED"},
    "ACTED": {"RECOVERED", "STILL_FAILED"},
    "STILL_FAILED": {"SCHEDULED", "DONE"},  # SCHEDULED = next attempt, if under budget —
                                              # goes through RECONCILING again, correctly,
                                              # since real time has passed since the last one
    "RECOVERED": {"DONE"},
    "EXCLUDED": set(),
    "NOT_WORKED": set(),  # the gate's deliberate economic non-action (break_even_floor) —
                            # never conflated with REFUSED, the same distinction the
                            # frontend's "policy" tone vs "stop" tone already enforces
    "NEEDS_REVIEW": set(),  # human resolves out of band — out of scope for Day 1
    "REFUSED": set(),  # every other terminal gate rejection (hard_decline_stop,
                         # already_resolved, network_attempt_budget_exhausted,
                         # stale_reconcile) — none of these route to a human or reflect
                         # a deliberate economic choice; they're a flat, permanent no
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
