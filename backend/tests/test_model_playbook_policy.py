"""ModelPlaybookPolicy against the real, committed placeholder file (data/
playbook_v0_placeholder.json) -- scarcity_remaining_budget_threshold=1,
defer_priority_cutoff=1.2, soft weight=1.5 (clears the cutoff), technical weight=1.0
(below the cutoff). NETWORK_ATTEMPT_BUDGET_PER_CARD_30D=6, so 'scarce' means
card_attempts_in_window >= 5 (remaining <= 1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.harness.policies import ModelPlaybookPolicy, ObservableCase
from app.model.playbook_schema import AllocationRule, Playbook

PLACEHOLDER_PATH = Path(__file__).resolve().parent.parent / "data" / "playbook_v0_placeholder.json"


@pytest.fixture
def placeholder() -> Playbook:
    return Playbook(**json.loads(PLACEHOLDER_PATH.read_text()))


def _case(decline_class: str) -> ObservableCase:
    return ObservableCase(
        id="pay_test", amount=50_000, currency="INR", decline_class=decline_class,
        decline_class_source="documented", risk_flagged=False, card_id="card_test",
        simulated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _propose(playbook, decline_class, card_attempts_in_window):
    policy = ModelPlaybookPolicy(playbook, name="test_arm")
    return policy.propose(_case(decline_class), [], datetime(2026, 1, 1, tzinfo=timezone.utc), card_attempts_in_window)


def test_placeholder_file_loads_and_is_not_abstained(placeholder):
    assert placeholder.abstained is False
    assert placeholder.weight_for("soft") == 1.5
    assert placeholder.weight_for("technical") == 1.0


def test_not_scarce_always_retries_regardless_of_weight(placeholder):
    # remaining = 6 - 0 = 6, well above the threshold (1) -- not scarce.
    for decline_class in ("soft", "technical"):
        proposal = _propose(placeholder, decline_class, card_attempts_in_window=0)
        assert proposal.action_type == "retry_payment_link"
        assert proposal.amount_paise == 50_000


def test_scarce_and_below_cutoff_yields():
    # technical weight (1.0) < defer_priority_cutoff (1.2)
    proposal = _propose(_pb(), "technical", card_attempts_in_window=5)  # remaining = 1 <= threshold(1)
    assert proposal.action_type == "yield_scarce_budget"
    assert proposal.amount_paise is None


def test_scarce_but_at_or_above_cutoff_still_retries():
    # soft weight (1.5) >= defer_priority_cutoff (1.2) -- clears the cutoff, retries
    # even though the card is scarce.
    proposal = _propose(_pb(), "soft", card_attempts_in_window=5)
    assert proposal.action_type == "retry_payment_link"


def test_not_yet_scarce_at_the_boundary_still_retries():
    # remaining = 6 - 4 = 2 > threshold(1) -- not scarce yet, even for the low-weight class.
    proposal = _propose(_pb(), "technical", card_attempts_in_window=4)
    assert proposal.action_type == "retry_payment_link"


def test_exactly_at_the_scarcity_threshold_boundary_yields():
    # remaining = 6 - 5 = 1 == threshold(1) -- "at or below" includes equality.
    proposal = _propose(_pb(), "technical", card_attempts_in_window=5)
    assert proposal.action_type == "yield_scarce_budget"


def test_abstained_playbook_always_retries_regardless_of_scarcity_or_weight():
    abstained = _pb(abstained=True, abstain_reason="sensibility rate below threshold")
    # Even a maximally scarce card (remaining = 0) with the low-weight class must
    # still retry -- abstention falls back to RulesOnlyPolicy-identical behavior.
    proposal = _propose(abstained, "technical", card_attempts_in_window=6)
    assert proposal.action_type == "retry_payment_link"


def test_yield_proposal_never_carries_an_amount():
    """The yield branch never reaches the gate, so there's nothing to reconcile an
    amount against -- amount_paise stays None, unlike a retry proposal."""
    proposal = _propose(_pb(), "technical", card_attempts_in_window=6)
    assert proposal.action_type == "yield_scarce_budget"
    assert proposal.amount_paise is None


def _pb(**overrides) -> Playbook:
    defaults = dict(
        version="test-v0", synthesized_from_seed=42, provider="test", model_id="test-model",
        rules=[
            AllocationRule(decline_class="soft", priority_weight=1.5, rationale="soft > cutoff"),
            AllocationRule(decline_class="technical", priority_weight=1.0, rationale="technical < cutoff"),
        ],
        scarcity_remaining_budget_threshold=1,
        defer_priority_cutoff=1.2,
        abstained=False,
        abstain_reason=None,
    )
    defaults.update(overrides)
    return Playbook(**defaults)
