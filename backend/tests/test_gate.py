from datetime import datetime, timedelta, timezone

import pytest

from app.gate import GUARDRAIL_ORDER, ActionProposal, GateResult, evaluate
from app.models import PaymentCase
from app.policy_params import (
    AMOUNT_CEILING_PAISE,
    NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
    RECONCILE_FRESHNESS_WINDOW_SECONDS,
)


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


def test_break_even_floor_now_binds_at_the_last_reachable_attempt_for_a_tiny_payment():
    """REVISED finding, after the cost-unit-bug fix (₹0.115 is 11,500 milli-paise, not
    115 -- a 100x error). Under the WRONG cost, break-even never bound anywhere in the
    reachable window; under the corrected cost it does, exactly at attempt 6 (the last
    reachable one) for a ₹1 payment -- attempts 1-5 still clear it. Exhaustively
    checked, not asserted from one example, and the flip itself is the finding: a
    100x unit error changed the guardrail's real-world behavior, not just a decimal
    in a doc."""
    from app.policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D, expected_value_milli_paise

    evs = [
        expected_value_milli_paise("soft", n, amount_paise=100)
        for n in range(1, NETWORK_ATTEMPT_BUDGET_PER_CARD_30D + 1)  # 1..6, the reachable range
    ]
    assert all(ev >= 0 for ev in evs[:5]), "attempts 1-5 should still clear break-even for a ₹1 payment"
    assert evs[5] < 0, "attempt 6 should now be where break-even first binds for a ₹1 payment"


def test_break_even_expected_value_math_is_exact_integer():
    """No float ever enters the comparison — docs/assumptions.md's unit conventions."""
    from app.policy_params import expected_value_milli_paise

    ev = expected_value_milli_paise("soft", attempt_number=1, amount_paise=10_000)
    assert isinstance(ev, int)
    assert ev == 5_488_500  # (10000 * 1000 * 5500) // 10000 - 11500, pinned so a future
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


# --- GUARDRAIL_ORDER, proven exhaustively against evaluate()'s real behavior ---
#
# app.gate.GUARDRAIL_ORDER exists so a downstream display (Day 5's case audit screen)
# can show "which guardrails were actually evaluated before this one fired" without a
# second, possibly-diverging copy of the checked order. This section is what makes that
# safe: for every pair of guardrails, a single case is built to trip BOTH conditions at
# once (not just one at a time, which the tests above already cover) -- if
# GUARDRAIL_ORDER's order ever stops matching evaluate()'s real if-chain, one of these
# assertions fails.

# One independently-triggering set of overrides per guardrail. Case-level keys route
# through _case(); evaluate-level keys route through _evaluate(). break_even_floor's
# trigger (attempt_count_in_window=1000) is a deliberately extreme crafted probe, same
# technique as test_break_even_formula_goes_negative_for_an_extreme_crafted_input above:
# ATTEMPT_DECAY_FACTOR ** 999 rounds the effective recovery rate to 0 for ANY
# decline_class at ANY amount, so this one override alone makes
# expected_value_milli_paise negative regardless of anything else on the case --
# deliberately chosen to also be >= NETWORK_ATTEMPT_BUDGET_PER_CARD_30D, so merging it
# with network_attempt_budget_exhausted's own trigger (a smaller value) below is safe:
# whichever value wins the merge still satisfies both guardrails' conditions.
_TRIGGER: dict[str, dict] = {
    "stale_reconcile": {"reconciled_age_seconds": RECONCILE_FRESHNESS_WINDOW_SECONDS + 1},
    "unclassifiable_decline_human_review": {"decline_class": "unknown"},
    "hard_decline_stop": {"decline_class": "hard"},
    "risk_hard_stop": {"risk_flagged": True},
    "already_resolved": {"reconciled_status": "captured"},
    "amount_ceiling_needs_signoff": {"amount_paise": AMOUNT_CEILING_PAISE + 1},
    "network_attempt_budget_exhausted": {"attempt_count_in_window": NETWORK_ATTEMPT_BUDGET_PER_CARD_30D},
    "break_even_floor": {"attempt_count_in_window": 1000},
}
_CASE_LEVEL_KEYS = {"decline_class", "risk_flagged"}
_REAL_GUARDRAILS = [g for g in GUARDRAIL_ORDER if g != "permitted"]

# The one pair with no ordering ambiguity to resolve: decline_class is a single field,
# so a case cannot simultaneously BE "unknown" (guardrail 2's trigger) and "hard"
# (guardrail 3's trigger) -- they can never both apply to the same case, in production
# or in a crafted one, so there is nothing for this test to prove between them.
_STRUCTURALLY_EXCLUSIVE_PAIRS = {
    frozenset({"unclassifiable_decline_human_review", "hard_decline_stop"}),
}


def test_guardrail_order_constant_matches_every_pairwise_short_circuit():
    """Exhaustive, not spot-checked: for every pair (earlier, later) in GUARDRAIL_ORDER,
    a case built to trip BOTH independently comes back with the earlier one's reason.
    8 real guardrails -> 28 pairs, minus the 1 structurally-exclusive pair -> 27 proven."""
    tested = 0
    for i, earlier in enumerate(_REAL_GUARDRAILS):
        for later in _REAL_GUARDRAILS[i + 1:]:
            if frozenset({earlier, later}) in _STRUCTURALLY_EXCLUSIVE_PAIRS:
                continue
            case_kwargs: dict = {}
            eval_kwargs: dict = {}
            for name in (earlier, later):
                for k, v in _TRIGGER[name].items():
                    (case_kwargs if k in _CASE_LEVEL_KEYS else eval_kwargs)[k] = v
            result = _evaluate(_case(**case_kwargs), **eval_kwargs)
            assert result.reason == earlier, (
                f"{earlier!r} should short-circuit before {later!r} ever runs, got "
                f"{result.reason!r} for case_kwargs={case_kwargs} eval_kwargs={eval_kwargs}"
            )
            tested += 1
    assert tested == 27, f"expected to exercise 27 pairs, exercised {tested} -- a pair was silently skipped"


def test_guardrail_order_constant_is_exactly_the_documented_8_plus_permitted():
    assert GUARDRAIL_ORDER == (
        "permitted", "stale_reconcile", "unclassifiable_decline_human_review", "hard_decline_stop",
        "risk_hard_stop", "already_resolved", "amount_ceiling_needs_signoff",
        "network_attempt_budget_exhausted", "break_even_floor",
    )
