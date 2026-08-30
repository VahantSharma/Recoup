from datetime import datetime, timezone

import pytest

from app.intake import ARMS, apply_do_not_disturb, assign_arms_stratified
from app.models import PaymentCase
from app.state_machine import IllegalTransition


def test_deterministic_under_the_same_seed():
    classes = ["soft"] * 20 + ["hard"] * 5 + ["technical"] * 7
    assert assign_arms_stratified(classes, seed=42) == assign_arms_stratified(classes, seed=42)


def test_different_seed_can_produce_a_different_assignment():
    classes = ["soft"] * 20
    a = assign_arms_stratified(classes, seed=1)
    b = assign_arms_stratified(classes, seed=2)
    assert a != b


def test_only_known_arms_are_used():
    arms = assign_arms_stratified(["soft"] * 40, seed=42)
    assert set(arms) <= set(ARMS)


# --- do-not-disturb: the intake-time exclusion docs/ENGINEERING-DOCTRINE.md's guardrail table names,
# wired here for the DB-model/state-machine path (app.harness.run has its own,
# separate wiring for the in-memory ablation path -- see test_harness_run.py) ---

def _now():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _classified_case(opt_out: bool) -> PaymentCase:
    return PaymentCase(
        razorpay_payment_id="pay_dnd_test", amount=10_000, currency="INR",
        decline_class="soft", decline_class_source="documented", arm="rules_only",
        state="CLASSIFIED", opt_out=opt_out,
    )


def test_opted_out_case_is_excluded_instead_of_made_eligible():
    case = _classified_case(opt_out=True)
    excluded = apply_do_not_disturb(case, now=_now)
    assert excluded is True
    assert case.state == "EXCLUDED"
    assert case.excluded_reason == "opted_out"
    assert case.state_updated_at == _now()


def test_non_opted_out_case_is_left_untouched():
    case = _classified_case(opt_out=False)
    excluded = apply_do_not_disturb(case, now=_now)
    assert excluded is False
    assert case.state == "CLASSIFIED"  # unchanged -- caller proceeds to ELIGIBLE itself
    assert case.excluded_reason is None


def test_calling_out_of_order_fails_loudly_not_silently():
    """EXCLUDED is only a legal transition from CLASSIFIED (state_machine.py's
    LEGAL_TRANSITIONS) -- calling this on a case already past that point must raise,
    never silently do nothing and leave a caller believing exclusion happened."""
    case = _classified_case(opt_out=True)
    case.state = "ELIGIBLE"  # simulate a caller applying this too late
    with pytest.raises(IllegalTransition):
        apply_do_not_disturb(case, now=_now)


def test_stratum_proportions_are_balanced_when_evenly_divisible():
    arms = assign_arms_stratified(["soft"] * 40, seed=7)
    counts = {a: arms.count(a) for a in ARMS}
    assert all(c == 10 for c in counts.values())


def test_multiple_strata_are_each_balanced_independently():
    """8 hard-declines and 12 soft-declines in the same batch — each stratum should
    split evenly across the 4 arms on its own, not just in aggregate."""
    classes = ["hard"] * 8 + ["soft"] * 12
    arms = assign_arms_stratified(classes, seed=7)
    hard_arms, soft_arms = arms[:8], arms[8:]
    assert {a: hard_arms.count(a) for a in ARMS} == {a: 2 for a in ARMS}
    assert {a: soft_arms.count(a) for a in ARMS} == {a: 3 for a in ARMS}


def test_output_length_matches_input():
    classes = ["soft", "hard", "technical"]
    assert len(assign_arms_stratified(classes, seed=1)) == len(classes)
