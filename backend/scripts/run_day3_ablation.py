"""Day 3 checkpoint: the real ablation at n>=1000. Per the plan, this stops here —
shown before anything (compliance framing, sweeps) is built on top of these numbers.

Every number this script prints traces to the manifest printed at the top (git SHA,
corpus hash, full parameter set) -- if a figure in docs/results.md can't be traced to
that manifest, it doesn't belong in the file. See app/manifest.py.

Run: cd backend && python -m scripts.run_day3_ablation
"""
from __future__ import annotations

import hashlib
import inspect
import json
import math
from datetime import datetime, timezone
from statistics import NormalDist

from app import manifest
from app.corpus_builder import build_corpus
from app.gate import GUARDRAIL_ORDER
from app.harness.compliance import break_even_penalty_paise, net_value_paise, total_violations
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_arm, run_arm_with_guardrail_counts
from app.harness.stats import paired_bootstrap_lift
from app.policy_params import (
    AMOUNT_CEILING_PAISE,
    ATTEMPT_DECAY_FACTOR,
    COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
    NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
    POLICY_PRIOR_RECOVERY_RATE_BPS,
    RECONCILE_FRESHNESS_WINDOW_SECONDS,
)
from app.simulator.params import ORGANIC_RECOVERY_RATE_BPS, P_CASE_RECOVERABLE_BPS, SIM_TRUE_RECOVERY_RATE_BPS
from app.taxonomy import HARD, UNKNOWN

# Directly fetched, cited -- not assumed. See docs/assumptions.md's Compliance economics.
USD_TO_INR = 95.70  # Xe.com mid-market rate, 09:25 UTC, 23 Aug 2026

N = 1200
SEED = 42
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45

# Every 8 guardrails, in the gate's own checked order -- imported from app.gate, not
# redeclared here, so this script's guardrail table can never silently diverge from
# what evaluate() actually checks (see app.gate.GUARDRAIL_ORDER's own docstring and
# tests/test_gate.py's pairwise-ordering proof).

# Per-guardrail reachability verdict, worked out by tracing the gate's checked order
# against what the harness actually feeds it -- not guessed, not left implicit. See
# docs/results.md's Reachability table for the full write-up.
REACHABILITY = {
    "stale_reconcile": (
        False,
        "harness always calls gate.evaluate() with reconciled_at == now (age_seconds "
        "== 0 always) -- this guardrail guards a real production race (a stale local "
        "read vs. Razorpay's live state) that has no analog when the harness IS the "
        "live state. Acceptable: independently unit-tested (test_gate.py); simulating "
        "staleness would mean deliberately feeding the gate a wrong 'now', which tests "
        "the guardrail in isolation better than a corpus-level fluke would.",
    ),
    "unclassifiable_decline_human_review": (
        True,
        "was unreachable before this round (corpus only ever generated documented "
        "taxonomy reasons) -- fixed via unknown_reason_rate_bps, which injects reason "
        "strings absent from REASON_TAXONOMY at a small independent rate, the same "
        "pattern as risk_flag_rate_bps below.",
    ),
    "hard_decline_stop": (True, "RulesOnlyPolicy proposes a retry for every decline class alike; the gate, not the policy, is what stops hard declines."),
    "risk_hard_stop": (
        True,
        "was unreachable before this round (the only taxonomy reason carrying "
        "risk_flagged=True is HARD-classified, so hard_decline_stop always caught it "
        "first) -- fixed via risk_flag_rate_bps, an independent per-case risk draw.",
    ),
    "already_resolved": (
        False,
        "structurally distinct from stale_reconcile, not the same reason restated: "
        "reconciled_payment is hardcoded to {'status': 'failed'} for every gate call, "
        "AND the event queue is a strict chronological min-heap, so any case whose "
        "true organic resolution has already occurred by 'now' has already had its "
        "ORGANIC event processed (which sets recovered=True and halts all further "
        "events for that case) before any later-timed gate call could ever be reached. "
        "The harness cannot construct a case that reaches the gate with a stale "
        "'failed' status after it has actually resolved -- not because reconcile is "
        "fresh, but because a resolved case never reaches another gate call at all. "
        "Acceptable for the same reason stale_reconcile is: independently unit-tested "
        "(test_gate.py), and it guards a real production race with no analog in a "
        "single-threaded, chronologically-ordered simulation.",
    ),
    "amount_ceiling_needs_signoff": (True, "fires whenever a non-hard, non-unknown, non-risk-flagged case's amount clears AMOUNT_CEILING_PAISE."),
    "network_attempt_budget_exhausted": (True, "fires once a card's rolling-30-day attempt count reaches NETWORK_ATTEMPT_BUDGET_PER_CARD_30D -- see card_reuse_factor's HEADLINE RISK entry."),
    "break_even_floor": (
        False,
        "known dead within reachable parameters at this corpus's ticket sizes -- see "
        "docs/assumptions.md's cost_per_contact_attempt_milli_paise finding: it only "
        "binds at the last reachable attempt (6) for payments near Rs1, far below "
        "this corpus's ticket-size distribution. Acceptable: independently proven to "
        "bind on a crafted extreme input (attempt 40, Rs1) via "
        "expected_value_milli_paise() called directly, and its binding boundary "
        "within the budget's reachable window is exhaustively tested attempt-by-attempt.",
    ),
}


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def _corpus_params() -> dict:
    """The exact keyword defaults build_corpus() is called with below -- introspected
    from the function signature rather than hand-duplicated, so this manifest can't
    silently drift from what actually ran (the same class of bug a hand-typed second
    copy of a parameter value has caused twice already in docs/assumptions.md)."""
    sig = inspect.signature(build_corpus)
    return {
        name: p.default for name, p in sig.parameters.items()
        if p.default is not inspect.Parameter.empty
    }


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=N, seed=SEED, batch_simulated_start_at=start)

    params = {
        "n": N, "seed": SEED, "batch_simulated_start_at": start.isoformat(),
        "retry_delay_hours": RETRY_DELAY_HOURS, "max_case_lifetime_days": MAX_CASE_LIFETIME_DAYS,
        "corpus": _corpus_params(),
        "policy_params": {
            "COST_PER_CONTACT_ATTEMPT_MILLI_PAISE": COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
            "ATTEMPT_DECAY_FACTOR": ATTEMPT_DECAY_FACTOR,
            "AMOUNT_CEILING_PAISE": AMOUNT_CEILING_PAISE,
            "NETWORK_ATTEMPT_BUDGET_PER_CARD_30D": NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
            "RECONCILE_FRESHNESS_WINDOW_SECONDS": RECONCILE_FRESHNESS_WINDOW_SECONDS,
            "POLICY_PRIOR_RECOVERY_RATE_BPS": POLICY_PRIOR_RECOVERY_RATE_BPS,
        },
        "simulator_params": {
            "ORGANIC_RECOVERY_RATE_BPS": ORGANIC_RECOVERY_RATE_BPS,
            "P_CASE_RECOVERABLE_BPS": P_CASE_RECOVERABLE_BPS,
            "SIM_TRUE_RECOVERY_RATE_BPS": SIM_TRUE_RECOVERY_RATE_BPS,
        },
        "usd_to_inr": USD_TO_INR,
    }
    params_hash = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:16]

    print("=== MANIFEST -- every figure below traces to this run ===")
    print(f"git_sha       = {manifest.git_sha()}")
    print(f"corpus_hash   = {manifest.corpus_hash(corpus)}")
    print(f"params_hash   = {params_hash}")
    print(f"db_path       = {manifest.db_path()}")
    print()

    # Built per-arm (not via run_ablation) so rules_only's guardrail firing counts can
    # be captured alongside its results -- identical outcomes either way, since
    # run_arm_with_guardrail_counts is the same event loop with an added counting
    # side channel (see app/harness/run.py).
    results = {
        "control": run_arm(corpus, ControlPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS),
        "blind_retry": run_arm(corpus, BlindRetryPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS),
    }
    results["rules_only"], guardrail_counts = run_arm_with_guardrail_counts(
        corpus, RulesOnlyPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS,
    )

    print(f"n={len(corpus)} cases, master_seed={SEED}\n")

    print("--- per-arm absolute numbers, THREE-way outcome split (not lift -- read these first) ---")
    for arm, rows in results.items():
        n = len(rows)
        n_recovered = sum(r.recovered for r in rows)
        n_deferred = sum(r.outcome == "deferred_to_human_review" for r in rows)
        n_not_recovered = sum(r.outcome == "not_recovered" for r in rows)
        total_attempts = sum(r.attempt_count for r in rows)
        arm_violations = total_violations(rows)
        recovered_amount = sum(r.amount_paise for r in rows if r.recovered)
        deferred_amount = sum(r.amount_paise for r in rows if r.outcome == "deferred_to_human_review")
        print(
            f"{arm:>12}: recovered={n_recovered/n:.3%}  deferred_to_human_review={n_deferred/n:.3%}  "
            f"not_recovered={n_not_recovered/n:.3%}"
        )
        print(
            f"{'':>12}  total_attempts={total_attempts}  total_violations={arm_violations}  "
            f"recovered_amount={_fmt_paise(recovered_amount)}  deferred_amount={_fmt_paise(deferred_amount)}"
        )

    print("\n--- paired bootstrap lift (95% CI, 2000 resamples) ---")
    for arm_a, arm_b in (("rules_only", "control"), ("blind_retry", "control"), ("blind_retry", "rules_only")):
        lift = paired_bootstrap_lift(results[arm_a], results[arm_b], seed=7)
        print(f"\n{arm_a} vs {arm_b} (n={lift.n_cases}):")
        print(f"  recovery rate: {lift.rate_a:.3%} vs {lift.rate_b:.3%}")
        print(
            f"  rate lift:   {lift.rate_lift:+.4f}  "
            f"(95% CI [{lift.rate_lift_ci_low:+.4f}, {lift.rate_lift_ci_high:+.4f}])"
        )
        print(
            f"  amount lift: {_fmt_paise(lift.amount_lift_paise)}  "
            f"(95% CI [{_fmt_paise(lift.amount_lift_ci_low_paise)}, "
            f"{_fmt_paise(lift.amount_lift_ci_high_paise)}])"
        )

    print("\n--- compliance economics: break-even penalty rate (net value, not gross) ---")
    penalty_paise = break_even_penalty_paise(
        results["rules_only"], results["blind_retry"], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
    )
    penalty_usd = (penalty_paise / 100) / USD_TO_INR
    print(f"net_value(blind_retry) = {_fmt_paise(net_value_paise(results['blind_retry'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"net_value(rules_only)  = {_fmt_paise(net_value_paise(results['rules_only'], COST_PER_CONTACT_ATTEMPT_MILLI_PAISE))}")
    print(f"violations(blind_retry) = {total_violations(results['blind_retry'])}")
    print(f"break-even penalty = {_fmt_paise(penalty_paise)} per violation  (${penalty_usd:.2f} at 1 USD = Rs{USD_TO_INR})")
    print("  vs Visa $0.10/excess (Rs%.2f): break-even is ABOVE -> compliance doesn't pay on this alone" % (0.10 * USD_TO_INR))
    print("  vs Mastercard $1.00-$2.00/excess (Rs%.2f-Rs%.2f): break-even is BELOW -> compliance pays" % (1.00 * USD_TO_INR, 2.00 * USD_TO_INR))

    print("\n--- GUARDRAIL REACHABILITY TABLE, rules_only, every gate.evaluate() call ---")
    total_calls = sum(guardrail_counts.values())
    for reason in GUARDRAIL_ORDER:
        count = guardrail_counts.get(reason, 0)
        share = count / total_calls if total_calls else 0.0
        if reason == "permitted":
            print(f"  {reason:>36}: {count:>6}  ({share:.2%})  [not a guardrail -- gate approved]")
            continue
        reachable, why = REACHABILITY[reason]
        verdict = "REACHABLE" if reachable else "NOT reachable"
        print(f"  {reason:>36}: {count:>6}  ({share:.2%})  [{verdict}]")
    print(f"  {'total gate.evaluate() calls':>36}: {total_calls:>6}")
    print()
    for reason in GUARDRAIL_ORDER:
        if reason == "permitted":
            continue
        reachable, why = REACHABILITY[reason]
        print(f"  {reason} [{'REACHABLE' if reachable else 'NOT reachable'}]: {why}")
        print()

    print("--- deferred-bucket reconciliation (rules_only) ---")
    # Three disjoint-by-construction sets, matching the gate's own checked order
    # exactly (unknown before hard before risk before ceiling) -- each should equal
    # its own guardrail's firing count exactly, three independent cross-checks, not one.
    unknown_cases = [d for d in corpus if d.decline_class == UNKNOWN]
    nonhard_nonunknown = [d for d in corpus if d.decline_class not in (HARD, UNKNOWN)]
    risk_diverted = [d for d in nonhard_nonunknown if d.risk_flagged]
    ceiling_diverted = [d for d in nonhard_nonunknown if not d.risk_flagged and d.amount > AMOUNT_CEILING_PAISE]

    unknown_ids = {d.razorpay_payment_id for d in unknown_cases}
    risk_ids = {d.razorpay_payment_id for d in risk_diverted}
    ceiling_ids = {d.razorpay_payment_id for d in ceiling_diverted}
    union_ids = unknown_ids | risk_ids | ceiling_ids

    rules_by_id = {r.case_id: r for r in results["rules_only"]}
    would_defer_but_recovered_organically = sum(1 for cid in union_ids if rules_by_id[cid].recovered)
    actually_deferred = sum(1 for cid in union_ids if rules_by_id[cid].outcome == "deferred_to_human_review")
    unexpected = [cid for cid in union_ids if rules_by_id[cid].outcome not in ("recovered", "deferred_to_human_review")]

    print(f"  unknown-classified cases (any amount, any risk): {len(unknown_ids)}"
          f"  vs unclassifiable_decline_human_review count={guardrail_counts.get('unclassifiable_decline_human_review', 0)}")
    print(f"  risk-diverted non-hard non-unknown cases: {len(risk_ids)}"
          f"  vs risk_hard_stop count={guardrail_counts.get('risk_hard_stop', 0)}")
    print(f"  ceiling-diverted non-hard non-unknown non-risk-flagged cases: {len(ceiling_ids)}"
          f"  vs amount_ceiling_needs_signoff count={guardrail_counts.get('amount_ceiling_needs_signoff', 0)}")
    print(f"  union (every case whose first gate call routes to NEEDS_REVIEW): {len(union_ids)}")
    print(f"  of those, resolved organically anyway (outcome == recovered, not deferred): {would_defer_but_recovered_organically}")
    print(f"  actually reported outcome == 'deferred_to_human_review': {actually_deferred}")
    print(f"  arithmetic check: {len(union_ids)} - {would_defer_but_recovered_organically} = "
          f"{len(union_ids) - would_defer_but_recovered_organically}  (should equal actually_deferred above)")
    if unexpected:
        print(f"  UNEXPECTED: {len(unexpected)} case(s) in the union with neither outcome -- investigate: {unexpected[:5]}")

    print("\n  --- ceiling: generative-model-expected vs observed-at-guardrail (both directions) ---")
    corpus_params = _corpus_params()
    median_paise = corpus_params["ticket_size_median_paise"]
    sigma = corpus_params["ticket_size_sigma"]
    n_cases = len(corpus)
    z = (math.log(AMOUNT_CEILING_PAISE) - math.log(median_paise)) / sigma
    p_over_ceiling_theoretical = 1 - NormalDist().cdf(z)
    expected_over_ceiling = p_over_ceiling_theoretical * n_cases

    observed_over_ceiling_any_class = sum(1 for d in corpus if d.amount > AMOUNT_CEILING_PAISE)

    p_unknown = corpus_params["unknown_reason_rate_bps"] / 10_000
    p_hard_of_nonsoft = corpus_params["hard_share_of_nonsoft"]
    p_soft = corpus_params["soft_share"]
    p_hard = p_hard_of_nonsoft * (1 - p_soft)
    p_survives_unknown_and_hard = (1 - p_unknown) * (1 - p_hard)
    p_risk = corpus_params["risk_flag_rate_bps"] / 10_000
    p_survives_to_ceiling_check = p_survives_unknown_and_hard * (1 - p_risk)

    p_final = p_over_ceiling_theoretical * p_survives_to_ceiling_check
    expected_at_ceiling_guardrail = p_final * n_cases
    binomial_sd = math.sqrt(n_cases * p_final * (1 - p_final))
    observed_at_ceiling_guardrail = len(ceiling_ids)
    gap_sd = abs(observed_at_ceiling_guardrail - expected_at_ceiling_guardrail) / binomial_sd

    print(f"  theoretical P(amount > Rs{AMOUNT_CEILING_PAISE/100:,.0f}) from the log-normal CDF"
          f" (median=Rs{median_paise/100:,.0f}, sigma={sigma}): {p_over_ceiling_theoretical:.4%}")
    print(f"  expected over-ceiling count (any class), n={n_cases}: {expected_over_ceiling:.1f}")
    print(f"  observed over-ceiling count (any class): {observed_over_ceiling_any_class}")
    print(f"  guardrail-ordering survival: P(not unknown)={1-p_unknown:.4%} x P(not hard)={1-p_hard:.4%}"
          f" x P(not risk-flagged)={1-p_risk:.4%} = {p_survives_to_ceiling_check:.4%}")
    print(f"  expected count reaching amount_ceiling_needs_signoff: {expected_over_ceiling:.1f} x "
          f"{p_survives_to_ceiling_check:.4%} = {expected_at_ceiling_guardrail:.2f}")
    print(f"  binomial SD at n={n_cases}, p={p_final:.4%}: {binomial_sd:.2f}")
    print(f"  observed amount_ceiling_needs_signoff count: {observed_at_ceiling_guardrail}")
    print(f"  gap: {observed_at_ceiling_guardrail - expected_at_ceiling_guardrail:+.2f}  "
          f"({gap_sd:.2f} binomial SD -- {'within' if gap_sd < 2 else 'OUTSIDE'} the usual 2-SD noise band)")

    total_value = sum(d.amount for d in corpus)
    ceiling_value = sum(d.amount for d in ceiling_diverted)
    print(f"\n  ceiling-diverted count share: {len(ceiling_ids)/len(corpus):.2%} of {len(corpus)} cases")
    print(f"  ceiling-diverted value share: {ceiling_value/total_value:.2%} of total corpus Rs value")


if __name__ == "__main__":
    main()
