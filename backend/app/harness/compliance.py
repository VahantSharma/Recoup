"""Compliance framing for the ablation: violation counting (free — it's already on
every CaseArmResult from the gate's audit_only calls) and the break-even penalty rate
— the ₹-per-violation cost at which two arms produce equal NET value.

Solved on net value, not gross recovered amount — the first draft of this formula
compared gross ₹, which ignored that blind retry makes far more contact attempts than
rules_only and pays far more in messaging cost as a result. The reported penalty rate
would have been inflated by exactly the cost difference left out. See
docs/assumptions.md's Compliance economics section.
"""
from __future__ import annotations

from .run import CaseArmResult


def total_violations(rows: list[CaseArmResult]) -> int:
    return sum(r.violation_count for r in rows)


def net_value_paise(rows: list[CaseArmResult], cost_per_contact_attempt_milli_paise: int) -> float:
    """recovered amount minus the cost of every contact attempt actually made —
    'operating' value, before any violation penalty is priced in."""
    recovered = sum(r.amount_paise for r in rows if r.recovered)
    total_attempts = sum(r.attempt_count for r in rows)
    contact_cost_paise = total_attempts * cost_per_contact_attempt_milli_paise / 1000
    return recovered - contact_cost_paise


def break_even_penalty_paise(
    enforced_rows: list[CaseArmResult],
    audit_only_rows: list[CaseArmResult],
    cost_per_contact_attempt_milli_paise: int,
) -> float:
    """The ₹-per-violation cost at which `audit_only_rows`'s arm (e.g. blind_retry)
    and `enforced_rows`'s arm (e.g. rules_only) produce equal net value. Requires the
    enforced arm to have zero violations (true by construction — see gate.py: an
    enforced arm never acts against a rejection) and the audit-only arm to have at
    least one (otherwise there's nothing to solve for — dividing by its violation
    count)."""
    if total_violations(enforced_rows) != 0:
        raise ValueError(
            "the 'enforced' arm has nonzero violations -- break_even_penalty_paise "
            "assumes it never acts against a gate rejection (violation_count == 0 by "
            "construction for an enforced arm; pass the audit_only arm as the other argument)"
        )
    violations = total_violations(audit_only_rows)
    if violations == 0:
        raise ValueError("the audit-only arm has zero violations -- no penalty rate to solve for")

    net_audit_only = net_value_paise(audit_only_rows, cost_per_contact_attempt_milli_paise)
    net_enforced = net_value_paise(enforced_rows, cost_per_contact_attempt_milli_paise)
    return (net_audit_only - net_enforced) / violations
