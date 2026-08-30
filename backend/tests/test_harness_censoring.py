"""Proves the horizon choice doesn't bias arm comparison -- not just declares it.
docs/assumptions.md: horizon_days = arrival_window_days + max_case_lifetime_days + 10,
chosen so every case reaches a terminal outcome before the horizon, for every arm
identically -- zero censoring by construction. This measures that it actually holds,
at defaults and at the swept extremes of the two inputs the OAT sweep will vary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.corpus_builder import build_corpus
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_ablation


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _assert_no_case_exceeds_horizon(
    n: int, arrival_window_days: int, max_case_lifetime_days: int, seed: int = 42,
):
    horizon_days = arrival_window_days + max_case_lifetime_days + 10
    horizon_at = _start() + timedelta(days=horizon_days)

    corpus = build_corpus(
        n=n, seed=seed, batch_simulated_start_at=_start(), arrival_window_days=arrival_window_days,
    )
    results = run_ablation(
        corpus,
        [ControlPolicy(), BlindRetryPolicy(), RulesOnlyPolicy()],
        master_seed=seed,
        max_case_lifetime_days=max_case_lifetime_days,
    )

    for arm, rows in results.items():
        # Every case must reach SOME terminal final_status -- none left dangling.
        assert all(r.final_status != "" for r in rows)
        for r in rows:
            if r.resolved_at is not None:
                assert r.resolved_at <= horizon_at, (
                    f"{arm}/{r.case_id} resolved at {r.resolved_at}, past the declared "
                    f"horizon {horizon_at} -- the horizon formula is not generous enough"
                )


def test_no_case_exceeds_the_declared_horizon_at_default_params():
    _assert_no_case_exceeds_horizon(n=500, arrival_window_days=30, max_case_lifetime_days=45)


def test_no_case_exceeds_the_declared_horizon_at_swept_extremes():
    """arrival_window_days and max_case_lifetime_days are both swept (OAT and joint
    random) -- this is the test that would catch a future parameter range making
    censoring reachable, per the Day 3 plan's explicit instruction."""
    for arrival_window_days in (1, 60):
        for max_case_lifetime_days in (20, 90):
            _assert_no_case_exceeds_horizon(
                n=200, arrival_window_days=arrival_window_days,
                max_case_lifetime_days=max_case_lifetime_days,
            )


def test_every_case_reaches_a_real_terminal_status_not_left_in_progress():
    corpus = build_corpus(n=500, seed=42, batch_simulated_start_at=_start())
    results = run_ablation(corpus, [ControlPolicy(), RulesOnlyPolicy()], master_seed=42)
    valid_statuses = {
        "recovered", "not_recovered", "gave_up_gate_rejected", "gave_up_lifetime_exceeded",
        "excluded_opted_out",  # do-not-disturb -- injected by build_corpus() at its default rate now
    }
    for arm, rows in results.items():
        statuses = {r.final_status for r in rows}
        assert statuses <= valid_statuses, f"{arm} produced an unexpected status: {statuses - valid_statuses}"
