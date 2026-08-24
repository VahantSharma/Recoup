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
    use_common_random_numbers: bool = True,
) -> bool:
    """False unconditionally if the case was never recoverable — no action changes
    that. Otherwise a seeded roll against SIM_TRUE_RECOVERY_RATE_BPS.

    MEASUREMENT BUG, FOUND AND FIXED (see docs/results.md's "Common random numbers"
    section for the full writeup): this function used to key its RNG stream on `arm`
    as well as (case_id, attempt_number), on the reasoning that "different arms take a
    different number of attempts at different simulated times, so there's no natural
    draw to share across them." That reasoning is wrong for exactly the attempts that
    DO align — when two arms face the same case at the same attempt number under the
    same rate, common random numbers means they must draw the same uniform variate, so
    the only source of divergence between arms is a decision that actually differs.
    Keying on `arm` re-rolled that draw independently per arm even when two policies
    proposed an economically identical attempt on the same case, which reinflates the
    paired-difference estimator's variance back toward the unpaired case (point
    estimates stay unbiased -- each individual draw is still marginally correct -- but
    CIs computed against the old behavior were wider than the true paired design
    should produce, and any comparison that happened to select among many
    similarly-named or identically-parameterized candidates was, to that extent,
    selecting on noise rather than signal).

    use_common_random_numbers=True (the default): the seed is (master_seed, case_id,
    attempt_number) only -- `arm` is accepted for logging/API-compatibility but never
    enters the seed, so identical decisions give identical outcomes across every arm.
    False: the original, pre-fix behavior (arm included in the seed), kept runnable
    only so the old harness's empirical noise floor can be measured directly -- see
    tests/test_null_arm_lift_is_zero.py. Nothing in this codebase should ever call
    this with use_common_random_numbers=False outside that one measurement.
    """
    if not ground_truth.is_recoverable:
        return False
    rate_bps = params.SIM_TRUE_RECOVERY_RATE_BPS.get(decline_class, 0)
    if use_common_random_numbers:
        rng = random.Random(f"{master_seed}:{case_id}:{attempt_number}")
    else:
        rng = random.Random(f"{master_seed}:{case_id}:{arm}:{attempt_number}")
    return rng.random() < rate_bps / 10_000
