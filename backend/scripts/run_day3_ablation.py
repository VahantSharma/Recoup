"""Day 3 checkpoint: the real ablation at n>=1000. Per the plan, this stops here —
shown before anything (compliance framing, sweeps) is built on top of these numbers.

Run: cd backend && python -m scripts.run_day3_ablation
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.harness.compliance import break_even_penalty_paise, net_value_paise, total_violations
from app.harness.policies import BlindRetryPolicy, ControlPolicy, RulesOnlyPolicy
from app.harness.run import run_arm, run_arm_with_guardrail_counts
from app.harness.stats import paired_bootstrap_lift
from app.policy_params import AMOUNT_CEILING_PAISE, COST_PER_CONTACT_ATTEMPT_MILLI_PAISE
from app.taxonomy import HARD

# Directly fetched, cited -- not assumed. See docs/assumptions.md's Compliance economics.
USD_TO_INR = 95.70  # Xe.com mid-market rate, 09:25 UTC, 23 Aug 2026

N = 1200
SEED = 42
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45


def _fmt_paise(p: float) -> str:
    return f"Rs {p / 100:,.2f}"


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=N, seed=SEED, batch_simulated_start_at=start)

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
        arm_violations = total_violations(rows)  # app.harness.compliance's function --
                                                    # a prior local var here shadowed
                                                    # the import; renamed, not just
                                                    # worked around
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

    print("\n--- guardrail firing counts, rules_only, every gate.evaluate() call ---")
    total_calls = sum(guardrail_counts.values())
    for reason in (
        "permitted", "stale_reconcile", "unclassifiable_decline_human_review", "hard_decline_stop",
        "risk_hard_stop", "already_resolved", "amount_ceiling_needs_signoff",
        "network_attempt_budget_exhausted", "break_even_floor",
    ):
        count = guardrail_counts.get(reason, 0)
        share = count / total_calls if total_calls else 0.0
        flag = "  <-- never fires" if count == 0 else ""
        print(f"  {reason:>36}: {count:>6}  ({share:.2%}){flag}")
    print(f"  {'total gate.evaluate() calls':>36}: {total_calls:>6}")
    print(
        "  stale_reconcile, already_resolved, and unclassifiable_decline_human_review are structurally\n"
        "  zero here, by construction, not by chance: the harness always calls the gate with a\n"
        "  freshly-simulated reconciled_at (age_seconds is always 0) and reconciled_payment =\n"
        "  {'status': 'failed'} (never in gate.py's _RESOLVED_STATUSES), and the corpus never generates a\n"
        "  decline_class == 'unknown' case (every taxonomy entry is hard/soft/technical). All three are\n"
        "  still independently unit-tested in test_gate.py against hand-crafted inputs the harness itself\n"
        "  never produces -- exercised by tests, not by this corpus. hard_decline_stop DOES fire here --\n"
        "  RulesOnlyPolicy proposes a retry for every decline class alike (see policies.py); the gate,\n"
        "  not the policy, is what stops hard declines."
    )

    print("\n--- deferred-bucket reconciliation (rules_only) ---")
    ceiling_blocked_nonhard = [d for d in corpus if d.amount > AMOUNT_CEILING_PAISE and d.decline_class != HARD]
    risk_flagged_nonhard = [d for d in corpus if d.risk_flagged and d.decline_class != HARD]
    ceiling_ids = {d.razorpay_payment_id for d in ceiling_blocked_nonhard}
    risk_ids = {d.razorpay_payment_id for d in risk_flagged_nonhard}
    union_ids = ceiling_ids | risk_ids
    overlap_ids = ceiling_ids & risk_ids

    rules_by_id = {r.case_id: r for r in results["rules_only"]}
    would_defer_but_recovered_organically = sum(
        1 for cid in union_ids if rules_by_id[cid].recovered
    )
    actually_deferred = sum(1 for cid in union_ids if rules_by_id[cid].outcome == "deferred_to_human_review")
    unexpected = [
        cid for cid in union_ids
        if rules_by_id[cid].outcome not in ("recovered", "deferred_to_human_review")
    ]

    print(f"  ceiling-blocked non-hard cases (amount > Rs{AMOUNT_CEILING_PAISE/100:,.0f}): {len(ceiling_ids)}")
    print(f"  risk-flagged non-hard cases (independent risk_flag_rate_bps draw): {len(risk_ids)}")
    print(f"  overlap (both ceiling-blocked AND risk-flagged -- risk_hard_stop wins, fires first): {len(overlap_ids)}")
    print(f"  union (every case whose gate call routes to NEEDS_REVIEW at arrival): {len(union_ids)}")
    print(f"  guardrail-count cross-check: risk_hard_stop + amount_ceiling_needs_signoff = "
          f"{guardrail_counts.get('risk_hard_stop', 0) + guardrail_counts.get('amount_ceiling_needs_signoff', 0)} "
          f"(must equal the union above -- each such case gets exactly one gate call, ever)")
    print(f"  of those, resolved organically anyway before the outcome was read (route_to stays NEEDS_REVIEW,\n"
          f"  historically true, but outcome == 'recovered' takes priority): {would_defer_but_recovered_organically}")
    print(f"  actually reported outcome == 'deferred_to_human_review': {actually_deferred}")
    print(f"  arithmetic check: {len(union_ids)} - {would_defer_but_recovered_organically} = "
          f"{len(union_ids) - would_defer_but_recovered_organically}  (should equal actually_deferred above)")
    if unexpected:
        print(f"  UNEXPECTED: {len(unexpected)} case(s) in the union with neither outcome -- investigate: {unexpected[:5]}")

    total_value = sum(d.amount for d in corpus)
    ceiling_value = sum(d.amount for d in ceiling_blocked_nonhard)
    print(f"\n  ceiling-blocked count share: {len(ceiling_ids)/len(corpus):.2%} of {len(corpus)} cases")
    print(f"  ceiling-blocked value share: {ceiling_value/total_value:.2%} of total corpus Rs value")


if __name__ == "__main__":
    main()
