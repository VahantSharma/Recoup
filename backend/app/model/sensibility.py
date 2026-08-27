"""Deterministic sensibility checks -- the checks the schema itself can't express
(schema validity is necessary but not sufficient: a schema-valid PlaybookProposal can
still have a duplicate/missing decline_class, an absurdly large weight, a threshold
above the actual card budget, or a rationale that's on-topic gibberish). Used by
scripts/run_day4_bakeoff.py to compute the bake-off's sensibility-rate column, and to
build the SensibleCandidate values app.model.abstention's pre-registered rule scores.

Kept deterministic and free (no LLM judge) per the plan's own discipline.
"""
from __future__ import annotations

from .abstention import SensibleCandidate
from .playbook_schema import PlaybookProposal

# A cheap, deterministic on-topic proxy -- not a claim of semantic understanding, just
# a floor against pure gibberish or an off-topic response that happened to validate.
_TOPIC_KEYWORDS = (
    "retry", "attempt", "card", "budget", "scarce", "recover", "decline",
    "soft", "technical", "priority", "yield", "capacity", "slot",
)

SANE_WEIGHT_MAX = 100.0
SANE_CUTOFF_MAX = 100.0


def is_sensible(proposal: PlaybookProposal, network_attempt_budget_per_card_30d: int) -> tuple[bool, str]:
    """Returns (sensible, reason). reason is empty iff sensible."""
    classes = [r.decline_class for r in proposal.rules]
    if classes.count("soft") != 1:
        return False, f"expected exactly one 'soft' rule, got {classes.count('soft')}"
    if classes.count("technical") != 1:
        return False, f"expected exactly one 'technical' rule, got {classes.count('technical')}"

    for rule in proposal.rules:
        if not (0 < rule.priority_weight <= SANE_WEIGHT_MAX):
            return False, f"priority_weight {rule.priority_weight} outside sane range (0, {SANE_WEIGHT_MAX}]"
        if not any(kw in rule.rationale.lower() for kw in _TOPIC_KEYWORDS):
            return False, f"rationale has no on-topic keyword: {rule.rationale!r}"

    if not (0 <= proposal.scarcity_remaining_budget_threshold <= network_attempt_budget_per_card_30d):
        return False, (
            f"scarcity_remaining_budget_threshold {proposal.scarcity_remaining_budget_threshold} "
            f"outside [0, {network_attempt_budget_per_card_30d}] -- a threshold above the real "
            f"card budget is never reachable and therefore never meaningful"
        )
    if not (0 < proposal.defer_priority_cutoff <= SANE_CUTOFF_MAX):
        return False, f"defer_priority_cutoff {proposal.defer_priority_cutoff} outside sane range (0, {SANE_CUTOFF_MAX}]"

    return True, ""


def to_sensible_candidate(proposal: PlaybookProposal) -> SensibleCandidate:
    """Only call on a proposal that already passed is_sensible() -- assumes exactly
    one 'soft' and one 'technical' rule exist."""
    soft_weight = next(r.priority_weight for r in proposal.rules if r.decline_class == "soft")
    technical_weight = next(r.priority_weight for r in proposal.rules if r.decline_class == "technical")
    return SensibleCandidate(
        weight_ratio=soft_weight / technical_weight,
        defer_priority_cutoff=proposal.defer_priority_cutoff,
        scarcity_remaining_budget_threshold=proposal.scarcity_remaining_budget_threshold,
    )
