from datetime import datetime, timedelta, timezone

from app.simulator.outcomes import attempt_succeeds, draw_ground_truth
from app.simulator.params import ORGANIC_RECOVERY_RATE_BPS, P_CASE_RECOVERABLE_BPS


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_deterministic_under_same_inputs():
    a = draw_ground_truth("case_1", "soft", 42, _start(), 45)
    b = draw_ground_truth("case_1", "soft", 42, _start(), 45)
    assert a == b


def test_different_case_id_can_differ():
    a = draw_ground_truth("case_1", "soft", 42, _start(), 45)
    b = draw_ground_truth("case_2", "soft", 42, _start(), 45)
    assert a != b


def test_hard_decline_is_always_unrecoverable():
    for i in range(200):
        gt = draw_ground_truth(f"case_{i}", "hard", 42, _start(), 45)
        assert gt.is_recoverable is False
        assert gt.organic_resolves_at is None


def test_attempt_never_succeeds_when_not_recoverable_regardless_of_rate():
    unrecoverable = draw_ground_truth("case_x", "hard", 42, _start(), 45)
    assert unrecoverable.is_recoverable is False
    for attempt_number in range(1, 50):
        assert attempt_succeeds("case_x", "rules_only", attempt_number, "soft", 42, unrecoverable) is False


def test_recoverable_fraction_converges_to_declared_rate():
    n = 5000
    recoverable = sum(
        draw_ground_truth(f"case_{i}", "soft", 42, _start(), 45).is_recoverable for i in range(n)
    )
    target = P_CASE_RECOVERABLE_BPS["soft"] / 10_000
    assert abs(recoverable / n - target) < 0.02


def test_organic_resolution_fraction_among_recoverable_converges():
    n = 5000
    ground_truths = [draw_ground_truth(f"case_{i}", "soft", 42, _start(), 45) for i in range(n)]
    recoverable = [gt for gt in ground_truths if gt.is_recoverable]
    organic = sum(1 for gt in recoverable if gt.organic_resolves_at is not None)
    target = ORGANIC_RECOVERY_RATE_BPS["soft"] / 10_000
    assert abs(organic / len(recoverable) - target) < 0.03


def test_organic_resolution_time_is_within_the_cases_own_lifetime_window():
    start = _start()
    lifetime_days = 45
    for i in range(500):
        gt = draw_ground_truth(f"case_{i}", "technical", 42, start, lifetime_days)
        if gt.organic_resolves_at is not None:
            assert start <= gt.organic_resolves_at <= start + timedelta(days=lifetime_days)


def test_ground_truth_does_not_depend_on_arm():
    """draw_ground_truth takes no `arm` parameter by design — the per-case facts are
    shared identically across every arm that runs this case. This test exists so a
    future signature change can't silently reintroduce an arm dependency."""
    import inspect

    assert "arm" not in inspect.signature(draw_ground_truth).parameters


def test_attempt_success_is_arm_independent_under_common_random_numbers():
    """The fixed, default behavior (use_common_random_numbers=True): the whole point
    of common random numbers is that identical decisions give identical outcomes
    across arms, so the RNG stream must NOT vary with `arm` at all. This replaces
    test_attempt_success_can_differ_by_arm_for_the_same_case_and_attempt_number, which
    asserted the bug (arm-dependence) as intended behavior -- see
    docs/results.md's "Common random numbers" section."""
    gt = draw_ground_truth("case_shared", "soft", 42, _start(), 45)
    assert gt.is_recoverable  # otherwise this test can't distinguish anything
    results_by_arm = {
        arm: [attempt_succeeds("case_shared", arm, n, "soft", 42, gt) for n in range(1, 30)]
        for arm in ("blind_retry", "rules_only", "rules_plus_model")
    }
    assert len({tuple(v) for v in results_by_arm.values()}) == 1, (
        "under common random numbers, the same case at the same attempt number must "
        "succeed or fail identically regardless of which arm is asking"
    )


def test_attempt_success_can_differ_by_arm_when_common_random_numbers_disabled():
    """The pre-fix behavior, kept runnable ONLY to measure the old harness's noise
    floor directly (tests/test_null_arm_lift_is_zero.py) -- nothing in production
    code should ever pass use_common_random_numbers=False."""
    gt = draw_ground_truth("case_shared", "soft", 42, _start(), 45)
    assert gt.is_recoverable
    results_by_arm = {
        arm: [
            attempt_succeeds("case_shared", arm, n, "soft", 42, gt, use_common_random_numbers=False)
            for n in range(1, 30)
        ]
        for arm in ("blind_retry", "rules_only", "rules_plus_model")
    }
    assert len({tuple(v) for v in results_by_arm.values()}) > 1


def test_module_level_params_can_be_monkeypatched_for_a_sweep():
    """Regression guard for the sweep infrastructure: outcomes.py must read
    params.X at call time (module-qualified), not bind a name at import time --
    otherwise patching params.ORGANIC_RECOVERY_RATE_BPS for one sweep point would
    silently be a no-op here, and the whole sweep would quietly run every point
    against the unswept default."""
    import app.simulator.params as sim_params

    original = sim_params.ORGANIC_RECOVERY_RATE_BPS
    try:
        sim_params.ORGANIC_RECOVERY_RATE_BPS = {"hard": 0, "soft": 10_000, "technical": 10_000}
        # organic_recovery_rate_bps=10000 (100%) means every recoverable case must
        # organically resolve -- a directly observable behavior change.
        recoverable_but_not_organic = 0
        for i in range(300):
            gt = draw_ground_truth(f"patched_{i}", "soft", 99, _start(), 45)
            if gt.is_recoverable and gt.organic_resolves_at is None:
                recoverable_but_not_organic += 1
        assert recoverable_but_not_organic == 0
    finally:
        sim_params.ORGANIC_RECOVERY_RATE_BPS = original


def test_attempt_succeeds_is_deterministic():
    gt = draw_ground_truth("case_det", "soft", 42, _start(), 45)
    a = attempt_succeeds("case_det", "rules_only", 1, "soft", 42, gt)
    b = attempt_succeeds("case_det", "rules_only", 1, "soft", 42, gt)
    assert a == b
