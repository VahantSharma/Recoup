"""The compliance-aware policy gate. Deterministic, outside the model — the model
(later days) returns a *proposal* in a constrained schema; this decides whether it's
permitted. Never itself performs a money-touching action; the caller acts only when
`decision == "approved"`.

Guardrail order is deterministic and short-circuits on the first hit — each one is
independently testable (see tests/test_gate.py), matching docs/ENGINEERING-DOCTRINE.md's "per-guardrail
unit tests" requirement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import policy_params
from .models import PaymentCase

APPROVED = "approved"
REJECTED = "rejected"

NEEDS_REVIEW = "NEEDS_REVIEW"
NOT_WORKED = "NOT_WORKED"

# The gate's real checked order, numbered to match evaluate()'s own comments exactly.
# Exists so any downstream consumer that needs to display "which guardrails were
# actually evaluated before this one fired" (Day 5's case audit screen) reads the same
# order the gate itself checks -- imported, never re-declared elsewhere. Additive only:
# evaluate()'s behavior is unchanged by this constant's existence.
# tests/test_gate.py::test_guardrail_order_constant_matches_every_pairwise_short_circuit
# proves this tuple's order against evaluate()'s actual behavior, not just its comments.
GUARDRAIL_ORDER: tuple[str, ...] = (
    "permitted",
    "stale_reconcile",
    "unclassifiable_decline_human_review",
    "hard_decline_stop",
    "risk_hard_stop",
    "already_resolved",
    "amount_ceiling_needs_signoff",
    "network_attempt_budget_exhausted",
    "break_even_floor",
)

# The ONLY reconciled status that affirmatively confirms "this payment is still
# failed and was never collected" -- the one state in which a retry is even safe to
# consider. Default-deny, not default-allow: an ADVERSARIAL PASS FINDING (see
# docs/audit.md) -- this used to be `_RESOLVED_STATUSES = {"captured"}`, an allowlist
# of the one known ALREADY-resolved status, with every OTHER status (authorized,
# refunded, an unrecognized string, a typo, a status Razorpay adds after this was
# written) falling through as "not resolved" and proceeding toward approval. That is
# backwards for a system that moves money: an unrecognized reconciled state is a
# reason to stop and get a human's eyes on it, never a reason to proceed. Inverted
# here -- 'failed' is the only value that passes; everything else refuses.
_ACTIONABLE_RECONCILED_STATUSES = {"failed"}


@dataclass(frozen=True)
class ActionProposal:
    action_type: str  # retry_payment_link | no_action | escalate_human
    amount_paise: int | None = None


@dataclass(frozen=True)
class GateResult:
    decision: str  # APPROVED | REJECTED
    reason: str  # which guardrail fired, or "permitted"
    route_to: str | None = None  # None | NEEDS_REVIEW | NOT_WORKED
    observed_status: str | None = None  # populated only by "already_resolved" -- the
        # actual reconciled status that caused the refusal (e.g. "captured",
        # "refunded", an unrecognized string), so the audit trail names exactly what
        # was observed rather than just that something didn't match. `reason` itself
        # stays a fixed, small vocabulary (GUARDRAIL_ORDER) on purpose -- every other
        # consumer (guardrail_counts dicts, the case-audit guardrail table, the
        # frontend) keys off `reason` as one of those 9 known strings, so the actual
        # status can never be interpolated into `reason` itself without breaking all
        # of them.


def evaluate(
    case: PaymentCase,
    proposal: ActionProposal,
    *,
    reconciled_payment: dict,
    reconciled_at: datetime,
    attempt_count_in_window: int,
    now: datetime,
    audit_only: bool = False,  # noqa: ARG001 — see module docstring: does not change
                                # this function's logic or return value. It documents
                                # intent at the call site and keeps the signature
                                # stable for both consumers: the enforcing arms only
                                # act when decision == "approved"; the blind-retry arm
                                # calls evaluate(..., audit_only=True), ignores
                                # `decision`, acts unconditionally, and logs a rejected
                                # GateResult as a compliance-violation record. One
                                # implementation, two consumers.
) -> GateResult:
    # 1. Reconcile freshness — unconditional, first. Nothing below can be trusted off
    #    a reconcile that's too old, including a decision to reject.
    age_seconds = (now - reconciled_at).total_seconds()
    if age_seconds > policy_params.RECONCILE_FRESHNESS_WINDOW_SECONDS:
        return GateResult(REJECTED, "stale_reconcile")

    # 2. Unrecognized decline reason — never auto-actioned. See taxonomy.classify's
    #    UNKNOWN handling: a silent default here would permit acting on a signal
    #    nobody has actually classified.
    if case.decline_class == "unknown":
        return GateResult(REJECTED, "unclassifiable_decline_human_review", NEEDS_REVIEW)

    # 3. Hard decline — terminal, no override.
    if case.decline_class == "hard":
        return GateResult(REJECTED, "hard_decline_stop")

    # 4. Risk hard-stop.
    if case.risk_flagged:
        return GateResult(REJECTED, "risk_hard_stop", NEEDS_REVIEW)

    # 5. Reconcile-before-act's actual enforcement point, default-deny: a retry is
    #    only ever considered when the reconciled status affirmatively confirms the
    #    payment is still failed. Anything else -- already collected via another
    #    channel, mid-flight (authorized), refunded, an unrecognized string, a typo,
    #    a status Razorpay adds after this was written -- refuses and routes to a
    #    human, never silently falls through toward approval on a status this gate
    #    has never verified means "still failed."
    observed_status = reconciled_payment.get("status")
    if observed_status not in _ACTIONABLE_RECONCILED_STATUSES:
        return GateResult(REJECTED, "already_resolved", NEEDS_REVIEW, observed_status=observed_status)

    # 6. Amount ceiling.
    amount = proposal.amount_paise if proposal.amount_paise is not None else case.amount
    if amount > policy_params.AMOUNT_CEILING_PAISE:
        return GateResult(REJECTED, "amount_ceiling_needs_signoff", NEEDS_REVIEW)

    # 7. Network attempt budget.
    if attempt_count_in_window >= policy_params.NETWORK_ATTEMPT_BUDGET_PER_CARD_30D:
        return GateResult(REJECTED, "network_attempt_budget_exhausted")

    # 8. Break-even floor — the recovery-rate prior for the attempt about to be made
    #    (decayed from attempt 1's base rate), never a flat first-attempt prior
    #    applied unconditionally. Integer bps/milli-paise math throughout — see
    #    docs/assumptions.md's unit conventions; no float enters this comparison.
    next_attempt_number = attempt_count_in_window + 1
    ev = policy_params.expected_value_milli_paise(case.decline_class, next_attempt_number, amount)
    if ev < 0:
        return GateResult(REJECTED, "break_even_floor", NOT_WORKED)

    # 9. Nothing blocked it.
    return GateResult(APPROVED, "permitted")
