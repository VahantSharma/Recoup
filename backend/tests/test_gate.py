from datetime import datetime, timedelta, timezone

import pytest

from app.gate import ActionProposal, GateResult, evaluate
from app.models import PaymentCase
from app.policy_params import AMOUNT_CEILING_PAISE, RECONCILE_FRESHNESS_WINDOW_SECONDS


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _case(**overrides) -> PaymentCase:
    defaults = dict(decline_class="soft", risk_flagged=False, amount=10_000)
    defaults.update(overrides)
    return PaymentCase(**defaults)


def _evaluate(case, *, amount_paise=10_000, reconciled_status="failed",
              reconciled_age_seconds=0, attempt_count_in_window=0, audit_only=False):
    return evaluate(
        case,
        ActionProposal(action_type="retry_payment_link", amount_paise=amount_paise),
        reconciled_payment={"status": reconciled_status},
        reconciled_at=_now() - timedelta(seconds=reconciled_age_seconds),
        attempt_count_in_window=attempt_count_in_window,
        now=_now(),
        audit_only=audit_only,
    )


# --- 1. stale reconcile — checked first, unconditionally ---

def test_rejects_stale_reconcile_even_for_an_otherwise_clean_case():
    result = _evaluate(_case(), reconciled_age_seconds=RECONCILE_FRESHNESS_WINDOW_SECONDS + 1)
    assert result == GateResult("rejected", "stale_reconcile", None)


def test_accepts_reconcile_right_at_the_freshness_boundary():
    result = _evaluate(_case(), reconciled_age_seconds=RECONCILE_FRESHNESS_WINDOW_SECONDS)
    assert result.reason != "stale_reconcile"


# --- 2. unknown decline ---

def test_rejects_unknown_decline_class_to_needs_review():
    result = _evaluate(_case(decline_class="unknown"))
    assert result == GateResult("rejected", "unclassifiable_decline_human_review", "NEEDS_REVIEW")


# --- 3. hard decline ---

def test_rejects_hard_decline_terminal_no_override():
    result = _evaluate(_case(decline_class="hard"))
    assert result == GateResult("rejected", "hard_decline_stop", None)


def test_hard_decline_stop_holds_even_under_audit_only():
    """audit_only doesn't change the gate's decision — only what the caller does with
    it. Proves the flag is genuinely a no-op on the gate's own logic."""
    enforcing = _evaluate(_case(decline_class="hard"), audit_only=False)
    audit = _evaluate(_case(decline_class="hard"), audit_only=True)
    assert enforcing == audit


# --- 4. risk hard-stop ---

def test_rejects_risk_flagged_case_to_needs_review():
    result = _evaluate(_case(risk_flagged=True))
    assert result == GateResult("rejected", "risk_hard_stop", "NEEDS_REVIEW")


# --- 5. reconcile-before-act's actual enforcement ---

def test_rejects_a_case_already_resolved_per_fresh_reconcile():
    result = _evaluate(_case(), reconciled_status="captured")
    assert result == GateResult("rejected", "already_resolved", None)


# --- 6. amount ceiling ---

def test_rejects_amount_above_ceiling_to_needs_review():
    result = _evaluate(_case(), amount_paise=AMOUNT_CEILING_PAISE + 1)
    assert result == GateResult("rejected", "amount_ceiling_needs_signoff", "NEEDS_REVIEW")


def test_accepts_amount_exactly_at_ceiling():
    result = _evaluate(_case(), amount_paise=AMOUNT_CEILING_PAISE)
    assert result.reason != "amount_ceiling_needs_signoff"


# --- 7. network attempt budget ---

def test_rejects_when_attempt_budget_exhausted():
    result = _evaluate(_case(), attempt_count_in_window=6)
    assert result == GateResult("rejected", "network_attempt_budget_exhausted", None)


def test_accepts_just_under_budget():
    result = _evaluate(_case(), attempt_count_in_window=5)
    assert result.reason != "network_attempt_budget_exhausted"


# --- 8. break-even floor — crafted, not relying on the corpus to produce one ---

def test_break_even_floor_does_not_fire_on_attempt_1_at_a_realistic_ticket_size():
    """The finding in docs/assumptions.md, proven: real messaging costs are too small
    relative to any realistic payment to bind on a first attempt."""
    result = _evaluate(_case(), amount_paise=10_000, attempt_count_in_window=0)
    assert result == GateResult("approved", "permitted", None)


def test_break_even_formula_goes_negative_for_an_extreme_crafted_input():
    """The pure formula, tested in isolation from evaluate()'s guardrail chain on
    purpose — attempt_count_in_window this high would already have been rejected by
    the network-attempt-budget guardrail (see the next test) before break-even is
    ever reached in practice. This proves the math itself is capable of going
    negative; it does not claim evaluate() ever reaches this state."""
    from app.policy_params import expected_value_milli_paise

    assert expected_value_milli_paise("soft", attempt_number=40, amount_paise=100) < 0


def test_break_even_floor_cannot_bind_within_the_attempt_budgets_reachable_window():
    """The precise version of the docs/assumptions.md finding, verified rather than
    estimated: the network-attempt-budget guardrail (6 attempts/30 days) caps
    attempt_count_in_window at 5 before break-even is ever evaluated (attempt_count
    == 6 is rejected by budget, one guardrail earlier). Within that entire reachable
    range (next_attempt 1..6), break-even does not bind for ANY payment of at least
    ₹1 (100 paise) at real messaging costs -- not just "not on attempt 1". Proven by
    exhaustively checking every reachable attempt number, not asserted from one
    example."""
    from app.policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D, expected_value_milli_paise

    for attempt_count_in_window in range(NETWORK_ATTEMPT_BUDGET_PER_CARD_30D):  # 0..5, the reachable range
        next_attempt = attempt_count_in_window + 1
        ev = expected_value_milli_paise("soft", next_attempt, amount_paise=100)
        assert ev >= 0, f"break-even fired at attempt {next_attempt} for a ₹1 payment — finding is wrong"


def test_break_even_expected_value_math_is_exact_integer():
    """No float ever enters the comparison — docs/assumptions.md's unit conventions."""
    from app.policy_params import expected_value_milli_paise

    ev = expected_value_milli_paise("soft", attempt_number=1, amount_paise=10_000)
    assert isinstance(ev, int)
    assert ev == 5_499_885  # (10000 * 1000 * 5500) // 10000 - 115, pinned so a future
                             # change to the formula or the sourced constants is visible


# --- 9. clean approval ---

def test_approves_a_clean_soft_decline_case():
    result = _evaluate(_case())
    assert result == GateResult("approved", "permitted", None)


# --- guardrail ordering ---

def test_stale_reconcile_takes_priority_over_hard_decline():
    """A stale reconcile rejects before decline_class is even consulted -- proves the
    ordering, not just that both guardrails individually work."""
    result = _evaluate(
        _case(decline_class="hard"),
        reconciled_age_seconds=RECONCILE_FRESHNESS_WINDOW_SECONDS + 1,
    )
    assert result.reason == "stale_reconcile"


def test_unknown_decline_takes_priority_over_amount_ceiling():
    result = _evaluate(_case(decline_class="unknown"), amount_paise=AMOUNT_CEILING_PAISE + 1)
    assert result.reason == "unclassifiable_decline_human_review"
