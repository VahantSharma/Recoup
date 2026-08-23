"""Draws each case's hidden ground truth and resolves whether a given attempt
succeeds — Recoup's actual outcome model. Never importable outside
backend/app/simulator/ — enforced structurally by tests/test_import_boundary.py.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import params

# Module-qualified access (`params.X`), not `from .params import X` -- the latter
# copies a name binding at import time, so a sweep that monkey-patches
# `params.ORGANIC_RECOVERY_RATE_BPS` for one run would silently be a no-op here. This
# mirrors the pattern app.gate already uses correctly for app.policy_params.


@dataclass(frozen=True)
class CaseGroundTruth:
    is_recoverable: bool
    # None if unrecoverable, or recoverable but the organic roll didn't happen at all.
    # When set, always within [case_simulated_at, case_simulated_at + max_case_lifetime_days] —
    # organic self-resolution can't happen before the case even failed.
    organic_resolves_at: datetime | None


def draw_ground_truth(
    case_id: str,
    decline_class: str,
    master_seed: int,
    case_simulated_at: datetime,
    max_case_lifetime_days: int,
) -> CaseGroundTruth:
    """One seeded draw per case — shared identically across every arm that runs this
    same case. That sharing is the paired design's whole point: organic 'noise' is
    common across arms for a given case, so differencing cancels most of it out,
    isolating what a policy's actions actually changed. Deliberately does not take an
    `arm` parameter — nothing here may vary by arm.
    """
    rng = random.Random(f"{master_seed}:{case_id}")

    recoverable_bps = params.P_CASE_RECOVERABLE_BPS.get(decline_class, 0)
    if not (rng.random() < recoverable_bps / 10_000):
        return CaseGroundTruth(is_recoverable=False, organic_resolves_at=None)

    organic_bps = params.ORGANIC_RECOVERY_RATE_BPS.get(decline_class, 0)
    if rng.random() < organic_bps / 10_000:
        offset_days = rng.uniform(0, max_case_lifetime_days)
        return CaseGroundTruth(
            is_recoverable=True,
            organic_resolves_at=case_simulated_at + timedelta(days=offset_days),
        )
    return CaseGroundTruth(is_recoverable=True, organic_resolves_at=None)


def attempt_succeeds(
    case_id: str,
    arm: str,
    attempt_number: int,
    decline_class: str,
    master_seed: int,
    ground_truth: CaseGroundTruth,
) -> bool:
    """False unconditionally if the case was never recoverable — no action changes
    that. Otherwise a seeded roll against SIM_TRUE_RECOVERY_RATE_BPS, independent per
    (arm, attempt_number): different arms take a different number of attempts at
    different simulated times, so there's no natural draw to share across them (unlike
    draw_ground_truth's per-case facts, which are shared).
    """
    if not ground_truth.is_recoverable:
        return False
    rate_bps = params.SIM_TRUE_RECOVERY_RATE_BPS.get(decline_class, 0)
    rng = random.Random(f"{master_seed}:{case_id}:{arm}:{attempt_number}")
    return rng.random() < rate_bps / 10_000
