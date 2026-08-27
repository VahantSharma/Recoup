"""Day 5, Stage 2's one artifact: case_audit.json. One failed payment, end to end --
failure reason with decline_class_source provenance, the guardrail table for the
decisive gate call (in real evaluation order, short-circuit point marked -- see
app.gate.GUARDRAIL_ORDER), the proposed action and whether it was permitted / refused /
deferred, the derived idempotency key, and the outcome including deliberate-non-action
final statuses.

Same corpus, same seed, same manifest as scripts/run_day3_ablation.py -- this script
adds a deeper per-case trace on top of that run, not a new one.

Curated cases, selected programmatically, never hand-picked:
  - pay_TSv8WoMc4OAEGG, the real Day 1 harvested payment -- always included, always
    default_case_id, whatever its own decisive guardrail turns out to be.
  - the first case per REACHABLE guardrail (5: unclassifiable_decline_human_review,
    hard_decline_stop, risk_hard_stop, amount_ceiling_needs_signoff,
    network_attempt_budget_exhausted) -- see docs/results.md's reachability table.
  - one baseline case whose decisive call was "permitted" and which recovered.
  - one CRAFTED case for break_even_floor, the one reachable-in-principle guardrail
    that doesn't bind at this corpus's ticket sizes (docs/results.md) -- built the same
    way tests/test_gate.py already does, via a direct gate.evaluate() call, never
    presented as a corpus row.
  - stale_reconcile and already_resolved are NOT reachable by any case, corpus or
    crafted -- they describe a property of the harness itself (see docs/results.md),
    not a per-case condition. Reported as structurally_unreachable_guardrails, text
    reused verbatim from run_day3_ablation.py's REACHABILITY dict, not re-derived.

Run: cd backend && python -m scripts.export_case_audit
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

from app import manifest as manifest_mod
from app.corpus_builder import build_corpus
from app.export import build_manifest, write_artifact
from app.export_schemas import (
    CaseAuditArtifact,
    CaseAuditRow,
    GateCallRow,
    GuardrailVerdictRow,
    UnreachableGuardrailNote,
)
from app.gate import ActionProposal, GUARDRAIL_ORDER
from app.gate import evaluate as gate_evaluate
from app.harness.policies import RulesOnlyPolicy
from app.harness.run import run_arm_with_case_traces
from app.models import PaymentCase
from app.policy_params import (
    AMOUNT_CEILING_PAISE,
    ATTEMPT_DECAY_FACTOR,
    COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
    NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
    POLICY_PRIOR_RECOVERY_RATE_BPS,
    RECONCILE_FRESHNESS_WINDOW_SECONDS,
)
from app.simulator.params import ORGANIC_RECOVERY_RATE_BPS, P_CASE_RECOVERABLE_BPS, SIM_TRUE_RECOVERY_RATE_BPS
from app.state_machine import derive_idempotency_key
from scripts.run_day3_ablation import REACHABILITY

N = 1200
SEED = 42
RETRY_DELAY_HOURS = 24
MAX_CASE_LIFETIME_DAYS = 45
DEFAULT_CASE_ID = "pay_TSv8WoMc4OAEGG"

_REACHABLE_GUARDRAILS = (
    "unclassifiable_decline_human_review", "hard_decline_stop", "risk_hard_stop",
    "amount_ceiling_needs_signoff", "network_attempt_budget_exhausted",
)
_STRUCTURALLY_UNREACHABLE = ("stale_reconcile", "already_resolved")
_REAL_GUARDRAILS = [g for g in GUARDRAIL_ORDER if g != "permitted"]


def _corpus_params() -> dict:
    """Same introspection trick as run_day3_ablation.py -- can't silently drift from
    what build_corpus() was actually called with."""
    sig = inspect.signature(build_corpus)
    return {
        name: p.default for name, p in sig.parameters.items()
        if p.default is not inspect.Parameter.empty
    }


def _guardrail_table(reason: str) -> list[GuardrailVerdictRow]:
    """Walks GUARDRAIL_ORDER's real 8 guardrails (excluding "permitted") in their real
    checked order. Never runs a second evaluation path through the gate -- purely a
    presentation of the one reason evaluate() already returned, per Change 1 of the
    approved plan: no evaluate_all(), no hypothetical verdicts."""
    fired_index = len(_REAL_GUARDRAILS) if reason == "permitted" else _REAL_GUARDRAILS.index(reason)
    rows = []
    for i, name in enumerate(_REAL_GUARDRAILS):
        if i < fired_index:
            rows.append(GuardrailVerdictRow(name=name, evaluated=True, fired=False, note=""))
        elif i == fired_index:
            rows.append(GuardrailVerdictRow(name=name, evaluated=True, fired=True, note=""))
        else:
            rows.append(GuardrailVerdictRow(
                name=name, evaluated=False, fired=False,
                note=f"not evaluated -- short-circuited at {reason}",
            ))
    return rows


def _gate_call_row(case_id: str, trace) -> GateCallRow:
    return GateCallRow(
        attempt_number=trace.attempt_number, at=trace.now,
        proposal_action_type=trace.proposal_action_type, proposal_amount_paise=trace.proposal_amount_paise,
        decision=trace.decision, reason=trace.reason, route_to=trace.route_to,
        idempotency_key=derive_idempotency_key(case_id, trace.attempt_number),
        guardrail_table=_guardrail_table(trace.reason),
    )


def _case_row_from_corpus(draft, result, traces) -> CaseAuditRow:
    return CaseAuditRow(
        case_id=draft.razorpay_payment_id, case_kind="corpus", crafted_note=None,
        decline_class=draft.decline_class, decline_class_source=draft.decline_class_source,
        error_code=draft.error_code, error_reason=draft.error_reason, error_description=draft.error_description,
        amount_paise=draft.amount,
        gate_calls=[_gate_call_row(draft.razorpay_payment_id, t) for t in traces],
        final_status=result.final_status, route_to=result.route_to, outcome=result.outcome,
    )


def _crafted_break_even_case() -> CaseAuditRow:
    """Same technique tests/test_gate.py's break-even tests already use: a hand-built
    PaymentCase and a direct gate.evaluate() call, never run through the harness. Not
    reachable at this corpus's ticket sizes (docs/results.md) -- shown honestly as
    crafted, never blended in as a corpus row."""
    case_id = "crafted-break_even_floor"
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    amount_paise = 100  # Rs 1 -- the exact figure docs/results.md's finding uses
    attempt_count_in_window = 5  # next_attempt_number = 6, the last reachable attempt
                                   # under NETWORK_ATTEMPT_BUDGET_PER_CARD_30D
    case = PaymentCase(decline_class="soft", risk_flagged=False, amount=amount_paise)
    result = gate_evaluate(
        case, ActionProposal(action_type="retry_payment_link", amount_paise=amount_paise),
        reconciled_payment={"status": "failed"}, reconciled_at=now,
        attempt_count_in_window=attempt_count_in_window, now=now,
    )
    attempt_number = attempt_count_in_window + 1
    gate_call = GateCallRow(
        attempt_number=attempt_number, at=now, proposal_action_type="retry_payment_link",
        proposal_amount_paise=amount_paise, decision=result.decision, reason=result.reason,
        route_to=result.route_to, idempotency_key=derive_idempotency_key(case_id, attempt_number),
        guardrail_table=_guardrail_table(result.reason),
    )
    return CaseAuditRow(
        case_id=case_id, case_kind="crafted",
        crafted_note=(
            "break_even_floor is real and independently unit-tested (tests/test_gate.py), but "
            "does not bind anywhere in this corpus's ticket-size distribution -- it only fires "
            "at the last reachable attempt (6) for a payment near Rs 1, per docs/results.md's "
            "cost_per_contact_attempt_milli_paise finding. This case is a crafted illustration "
            "of that finding, not a case drawn from the corpus."
        ),
        decline_class="soft", decline_class_source="documented",
        error_code=None, error_reason=None, error_description=None, amount_paise=amount_paise,
        gate_calls=[gate_call], final_status="gave_up_gate_rejected", route_to=result.route_to,
        outcome="not_recovered",
    )


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    corpus = build_corpus(n=N, seed=SEED, batch_simulated_start_at=start)
    all_ids = frozenset(d.razorpay_payment_id for d in corpus)

    results, traces = run_arm_with_case_traces(
        corpus, RulesOnlyPolicy(), SEED, RETRY_DELAY_HOURS, MAX_CASE_LIFETIME_DAYS,
        trace_case_ids=all_ids,
    )
    drafts_by_id = {d.razorpay_payment_id: d for d in corpus}
    results_by_id = {r.case_id: r for r in results}

    def decisive_reason(case_id: str) -> str | None:
        case_traces = traces.get(case_id) or []
        return case_traces[-1].reason if case_traces else None

    selected_ids: list[str] = [DEFAULT_CASE_ID]  # always first, always included
    filled_branches: set[str] = set()
    default_reason = decisive_reason(DEFAULT_CASE_ID)
    if default_reason in _REACHABLE_GUARDRAILS:
        filled_branches.add(default_reason)
    elif default_reason == "permitted" and results_by_id[DEFAULT_CASE_ID].recovered:
        filled_branches.add("baseline_permitted_recovered")

    for draft in corpus:  # corpus order -- "first match," not hand-picked
        case_id = draft.razorpay_payment_id
        if case_id in selected_ids:
            continue
        reason = decisive_reason(case_id)
        if reason in _REACHABLE_GUARDRAILS and reason not in filled_branches:
            selected_ids.append(case_id)
            filled_branches.add(reason)
        elif (
            reason == "permitted" and results_by_id[case_id].recovered
            and "baseline_permitted_recovered" not in filled_branches
        ):
            selected_ids.append(case_id)
            filled_branches.add("baseline_permitted_recovered")
        if len(filled_branches) == len(_REACHABLE_GUARDRAILS) + 1:  # +1 for the baseline
            break

    cases = [
        _case_row_from_corpus(drafts_by_id[cid], results_by_id[cid], traces.get(cid, []))
        for cid in selected_ids
    ]
    cases.append(_crafted_break_even_case())

    unreachable_notes = [
        UnreachableGuardrailNote(name=name, why=REACHABILITY[name][1])
        for name in _STRUCTURALLY_UNREACHABLE
    ]

    manifest = build_manifest(
        script="scripts/export_case_audit.py", schema_name=CaseAuditArtifact.SCHEMA_NAME,
        schema_version=CaseAuditArtifact.SCHEMA_VERSION, seed=SEED,
        corpus_hash=manifest_mod.corpus_hash(corpus),
        policy_params={
            "COST_PER_CONTACT_ATTEMPT_MILLI_PAISE": COST_PER_CONTACT_ATTEMPT_MILLI_PAISE,
            "ATTEMPT_DECAY_FACTOR": ATTEMPT_DECAY_FACTOR,
            "AMOUNT_CEILING_PAISE": AMOUNT_CEILING_PAISE,
            "NETWORK_ATTEMPT_BUDGET_PER_CARD_30D": NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
            "RECONCILE_FRESHNESS_WINDOW_SECONDS": RECONCILE_FRESHNESS_WINDOW_SECONDS,
            "POLICY_PRIOR_RECOVERY_RATE_BPS": POLICY_PRIOR_RECOVERY_RATE_BPS,
        },
        simulator_params={
            "ORGANIC_RECOVERY_RATE_BPS": ORGANIC_RECOVERY_RATE_BPS,
            "P_CASE_RECOVERABLE_BPS": P_CASE_RECOVERABLE_BPS,
            "SIM_TRUE_RECOVERY_RATE_BPS": SIM_TRUE_RECOVERY_RATE_BPS,
        },
        use_common_random_numbers=True,
    )
    artifact = CaseAuditArtifact(
        default_case_id=DEFAULT_CASE_ID, cases=cases,
        structurally_unreachable_guardrails=unreachable_notes,
    )
    out_path = write_artifact(CaseAuditArtifact.SCHEMA_NAME, CaseAuditArtifact.SCHEMA_VERSION, manifest, artifact)

    print("=== MANIFEST -- case_audit.json ===")
    print(f"git_sha  = {manifest.git_sha}")
    print(f"corpus_hash = {manifest.corpus_hash}")
    print(f"wrote {out_path}")
    print(f"\n{len(cases)} cases ({len(selected_ids)} from corpus, 1 crafted):")
    for row in cases:
        decisive = row.gate_calls[-1].reason if row.gate_calls else "(no gate calls)"
        print(f"  [{row.case_kind:>6}] {row.case_id:<24} decline_class={row.decline_class:<10} "
              f"decisive={decisive:<40} outcome={row.outcome}")
    branches_covered = filled_branches | {"break_even_floor (crafted)"}
    missing = set(_REACHABLE_GUARDRAILS) - filled_branches
    if missing:
        print(f"\n  WARNING: no corpus case found for: {missing} -- consider a larger N")
    print(f"\nstructurally unreachable (no case, corpus or crafted): {_STRUCTURALLY_UNREACHABLE}")


if __name__ == "__main__":
    main()
