"""run_arm_with_case_traces -- the additive side-channel Day 5's case audit export
uses. Proves the three claims its own docstring/plan rely on: identical results to
run_arm for every case (not just the traced ones), traces populated only for the
requested ids, and every traced gate call's reason accounted for in app.gate's real
guardrail set.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.gate import GUARDRAIL_ORDER
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm, run_arm_with_case_traces


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _corpus(n=200, seed=42):
    return build_corpus(n=n, seed=seed, batch_simulated_start_at=_start())


def test_results_identical_to_run_arm_regardless_of_tracing():
    """The regression proof the plan calls for: tracing is a pure side channel, it
    changes nothing about what the arm actually decided or recorded."""
    corpus = _corpus()
    plain = run_arm(corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45)
    traced_ids = frozenset(d.razorpay_payment_id for d in corpus[:5])
    traced, _ = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45,
        trace_case_ids=traced_ids,
    )
    assert plain == traced


def test_traces_only_populated_for_requested_case_ids():
    corpus = _corpus()
    all_ids = [d.razorpay_payment_id for d in corpus]
    traced_ids = frozenset(all_ids[:3])
    _, traces = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45,
        trace_case_ids=traced_ids,
    )
    assert set(traces.keys()) <= traced_ids


def test_every_traced_gate_call_reason_is_a_real_guardrail_name():
    corpus = _corpus(n=500)
    all_ids = [d.razorpay_payment_id for d in corpus]
    traced_ids = frozenset(all_ids)  # trace everything at this small n -- exhaustive check
    _, traces = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45,
        trace_case_ids=traced_ids,
    )
    seen_reasons = {call.reason for calls in traces.values() for call in calls}
    assert seen_reasons <= set(GUARDRAIL_ORDER)


def test_empty_trace_case_ids_produces_no_traces_and_costs_nothing_extra():
    corpus = _corpus()
    results, traces = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45,
        trace_case_ids=frozenset(),
    )
    assert traces == {}
    assert len(results) == len(corpus)


def test_a_traced_case_with_multiple_gate_calls_records_them_in_attempt_order():
    """A permitted-then-eventually-rejected case (or any multi-attempt case) should
    show gate_calls with strictly increasing attempt_number -- proves the trace really
    is the full per-case decision trail, not just the last call."""
    corpus = _corpus(n=500)
    all_ids = [d.razorpay_payment_id for d in corpus]
    _, traces = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), master_seed=42, retry_delay_hours=24, max_case_lifetime_days=45,
        trace_case_ids=frozenset(all_ids),
    )
    multi_call_cases = [calls for calls in traces.values() if len(calls) > 1]
    assert multi_call_cases, "expected at least one traced case with more than one gate call at n=500"
    for calls in multi_call_cases:
        attempt_numbers = [c.attempt_number for c in calls]
        assert attempt_numbers == sorted(attempt_numbers)
        assert len(set(attempt_numbers)) == len(attempt_numbers)  # no duplicate attempt_number
