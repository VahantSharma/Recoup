"""Paired bootstrap over cases — not a normal approximation. Ticket sizes are
log-normal (sigma up to 1.8), so total recovered rupees is dominated by a handful of
large cases and its sampling distribution is badly skewed; a t-interval on the mean
would be miscalibrated and visibly wrong to a numerate judge. Two metrics, reported
separately and never collapsed into one — see docs/assumptions.md's Statistics
section.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .run import CaseArmResult


@dataclass(frozen=True)
class LiftResult:
    arm_a: str
    arm_b: str  # lift is reported as A minus B
    n_cases: int
    rate_a: float
    rate_b: float
    rate_lift: float  # point estimate: paired mean(recovered_a - recovered_b)
    rate_lift_ci_low: float
    rate_lift_ci_high: float
    amount_lift_paise: int  # point estimate: sum(amount_a - amount_b), paired
    amount_lift_ci_low_paise: float
    amount_lift_ci_high_paise: float


def _index_by_case(rows: list[CaseArmResult]) -> dict[str, CaseArmResult]:
    return {r.case_id: r for r in rows}


def paired_bootstrap_lift(
    arm_a_rows: list[CaseArmResult],
    arm_b_rows: list[CaseArmResult],
    *,
    n_bootstrap: int = 2000,
    seed: int = 0,
    ci: float = 0.95,
) -> LiftResult:
    """Resamples case *indices* with replacement, recomputes the paired difference per
    replicate, takes percentiles — not a formula assuming normality. The point
    estimate is the actual observed paired difference, not the bootstrap mean."""
    a_by_case = _index_by_case(arm_a_rows)
    b_by_case = _index_by_case(arm_b_rows)
    case_ids = sorted(set(a_by_case) & set(b_by_case))
    if not case_ids:
        raise ValueError("no overlapping cases between the two arms")

    d_rate: list[int] = []
    d_amount: list[int] = []
    for cid in case_ids:
        ra, rb = a_by_case[cid].recovered, b_by_case[cid].recovered
        d_rate.append(int(ra) - int(rb))
        amt_a = a_by_case[cid].amount_paise if ra else 0
        amt_b = b_by_case[cid].amount_paise if rb else 0
        d_amount.append(amt_a - amt_b)

    n = len(case_ids)
    rate_a = sum(a_by_case[cid].recovered for cid in case_ids) / n
    rate_b = sum(b_by_case[cid].recovered for cid in case_ids) / n
    point_rate_lift = sum(d_rate) / n
    point_amount_lift = sum(d_amount)

    rng = random.Random(seed)
    boot_rates: list[float] = []
    boot_amounts: list[int] = []
    for _ in range(n_bootstrap):
        idx = rng.choices(range(n), k=n)
        boot_rates.append(sum(d_rate[i] for i in idx) / n)
        boot_amounts.append(sum(d_amount[i] for i in idx))

    boot_rates.sort()
    boot_amounts.sort()
    alpha = (1 - ci) / 2
    lo_idx = max(0, int(alpha * n_bootstrap))
    hi_idx = min(n_bootstrap - 1, int((1 - alpha) * n_bootstrap) - 1)

    return LiftResult(
        arm_a=arm_a_rows[0].arm if arm_a_rows else "?",
        arm_b=arm_b_rows[0].arm if arm_b_rows else "?",
        n_cases=n,
        rate_a=rate_a,
        rate_b=rate_b,
        rate_lift=point_rate_lift,
        rate_lift_ci_low=boot_rates[lo_idx],
        rate_lift_ci_high=boot_rates[hi_idx],
        amount_lift_paise=point_amount_lift,
        amount_lift_ci_low_paise=boot_amounts[lo_idx],
        amount_lift_ci_high_paise=boot_amounts[hi_idx],
    )
