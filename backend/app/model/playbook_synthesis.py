"""Builds the real synthesis prompt from real, already-computed Day 3/4 run data --
no raw narration, no synthesized customer text, no invented numbers. Every figure in
the prompt is computed fresh here from an actual run over PROPOSAL_SEED's corpus, the
same corpus app.model.grid_search and app.harness.observable_optimal fit against --
never hand-typed from memory, per CLAUDE.md's "never fabricate a metric" rule.

Shared by both scripts/run_day4_bakeoff.py (20 calls/provider, measuring dispersion)
and scripts/synthesize_playbook.py (the one official call per provider) -- same
prompt, same PROPOSAL_SEED, so the bake-off's dispersion measurement is over the exact
prompt synthesis actually uses, not a stand-in.

Nothing here is called from anywhere under app/harness/ -- enforced by
tests/test_no_model_calls_in_reproducible_paths.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..corpus_builder import build_corpus
from ..harness.policies import RulesOnlyPolicy
from ..harness.run import run_arm, run_arm_with_guardrail_counts
from ..policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D
from .playbook_schema import PlaybookProposal
from .seeds import PROPOSAL_SEED

CORPUS_N = 1200
CORPUS_START = datetime(2026, 1, 1, tzinfo=timezone.utc)

GUARDRAIL_ORDER = (
    "permitted", "stale_reconcile", "unclassifiable_decline_human_review", "hard_decline_stop",
    "risk_hard_stop", "already_resolved", "amount_ceiling_needs_signoff",
    "network_attempt_budget_exhausted", "break_even_floor",
)


def compute_synthesis_stats(corpus=None) -> dict:
    """Every number below is computed from a real run, not hand-typed -- see the
    module docstring. corpus is an injectable parameter only for tests."""
    if corpus is None:
        corpus = build_corpus(n=CORPUS_N, seed=PROPOSAL_SEED, batch_simulated_start_at=CORPUS_START)

    rows, guardrail_counts = run_arm_with_guardrail_counts(
        corpus, RulesOnlyPolicy(), master_seed=PROPOSAL_SEED, retry_delay_hours=24, max_case_lifetime_days=45,
    )
    by_class: dict[str, list] = {"soft": [], "technical": [], "hard": []}
    for r in rows:
        by_class.setdefault(r.decline_class, []).append(r)

    per_class_stats = {}
    for cls in ("soft", "technical"):
        cls_rows = by_class.get(cls, [])
        n = len(cls_rows)
        if n == 0:
            continue
        recovered = sum(r.recovered for r in cls_rows)
        attempts = sum(r.attempt_count for r in cls_rows)
        amounts = [d.amount for d in corpus if d.decline_class == cls]
        per_class_stats[cls] = {
            "n": n,
            "recovery_rate": recovered / n,
            "mean_attempts_per_case": attempts / n,
            "median_ticket_paise": sorted(amounts)[len(amounts) // 2] if amounts else 0,
        }

    total_calls = sum(guardrail_counts.values())
    guardrail_shares = {name: guardrail_counts.get(name, 0) / total_calls for name in GUARDRAIL_ORDER if total_calls}

    n_cards = round(CORPUS_N / 4.0)  # card_reuse_factor default, see docs/assumptions.md
    capacity = n_cards * NETWORK_ATTEMPT_BUDGET_PER_CARD_30D
    total_attempts = sum(r.attempt_count for r in rows)
    budget_saturation = total_attempts / capacity if capacity else 0.0

    return {
        "per_class": per_class_stats,
        "guardrail_shares": guardrail_shares,
        "budget_saturation": budget_saturation,
        "network_attempt_budget_per_card_30d": NETWORK_ATTEMPT_BUDGET_PER_CARD_30D,
    }


def build_synthesis_prompt(stats: dict | None = None) -> str:
    if stats is None:
        stats = compute_synthesis_stats()

    lines = [
        "You are helping tune a payment-retry allocation policy for Recoup, a revenue-recovery",
        "system. Failed card payments are retried automatically, but every card has a shared,",
        f"scarce rolling-30-day attempt budget ({stats['network_attempt_budget_per_card_30d']} attempts per card),",
        "and multiple failed payments can share the same card. Below is REAL, measured data from",
        "one batch of 1,200+ cases run through the current rules-based policy (which retries every",
        "eligible case blindly, with no allocation logic at all):",
        "",
        "Per decline-class statistics (soft = insufficient funds / temporary issuer unavailability;",
        "technical = gateway timeout / network error, no real issuer decision reached):",
    ]
    for cls, s in stats["per_class"].items():
        lines.append(
            f"  - {cls}: n={s['n']} cases, recovery_rate={s['recovery_rate']:.1%}, "
            f"mean_attempts_per_case={s['mean_attempts_per_case']:.2f}, "
            f"median_ticket=Rs{s['median_ticket_paise']/100:,.0f}"
        )
    lines += [
        "",
        f"Shared card attempt-budget saturation: {stats['budget_saturation']:.1%} of theoretical capacity is",
        "already consumed by the current blind policy -- cards are heavily contended.",
        "",
        "Guardrail outcomes (share of all gate decisions):",
    ]
    for name, share in stats["guardrail_shares"].items():
        if name == "permitted":
            continue
        lines.append(f"  - {name}: {share:.2%}")
    lines += [
        "",
        "Your task: propose an allocation policy that decides, ONLY when a card's remaining",
        "rolling-30-day budget is scarce, whether a case should voluntarily yield its attempt this",
        "round (permanently -- a yielded case is never retried again) so a different case sharing",
        "that card can use the freed slot instead. You may NOT change whether a case is retried at",
        "all when the card is not scarce, and you may NOT propose anything about hard declines,",
        "risk-flagged cases, amount ceilings, or reconciliation -- those are enforced separately and",
        "are not yours to change.",
        "",
        "Respond with:",
        "  - one AllocationRule per decline class (soft, technical): a priority_weight (float > 0,",
        "    higher = more important to keep attempting) and a short rationale (under 280 chars)",
        "  - scarcity_remaining_budget_threshold (integer >= 0): how few remaining attempts on a",
        "    card counts as 'scarce'",
        "  - defer_priority_cutoff (float > 0): a case yields when scarce AND its class's weight is",
        "    below this cutoff",
        "",
        "Respond as JSON matching the given schema exactly.",
    ]
    return "\n".join(lines)
