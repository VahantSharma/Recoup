"""Resamples Razorpay's 16 documented reason strings into the real envelope shape
confirmed live on Day 1, against distributions from docs/assumptions.md — every
parameter here is a row there first. The one real harvested failure is concatenated in
untouched, never resampled or overwritten.

Deliberately does NOT import app.policy_params or app.simulator — a corpus is generic
data, not a policy decision or a simulated outcome. The gate and (Day 3) the simulator
each bring their own parameters to bear on this corpus separately.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .taxonomy import HARD, SOFT, TECHNICAL, REASON_TAXONOMY, classify

HARVESTED_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "harvested_corpus.json"


@dataclass
class CaseDraft:
    """A not-yet-persisted case — same shape as the relevant PaymentCase columns,
    minus id/batch_id which get assigned at insert time."""

    razorpay_payment_id: str
    razorpay_order_id: str | None
    card_id: str | None
    amount: int  # paise
    currency: str
    error_code: str | None
    error_reason: str | None
    error_description: str | None
    error_source: str | None
    error_step: str | None
    decline_class: str
    decline_class_source: str
    risk_flagged: bool
    simulated_at: datetime


def _load_harvested_failures() -> list[dict]:
    corpus = json.loads(HARVESTED_CORPUS_PATH.read_text(encoding="utf-8"))
    return [e["payment"] for e in corpus["entries"] if e["payment"]["status"] == "failed"]


def _rand_hex(rng: random.Random, nbytes: int = 8) -> str:
    """Seeded id generation — uuid.uuid4() draws from OS randomness and would silently
    break determinism under a fixed seed. Caught by test_deterministic_under_same_seed
    actually failing on the first run, not assumed correct."""
    return "".join(rng.choices("0123456789abcdef", k=nbytes * 2))


def _reasons_for_class(decline_class: str) -> list[str]:
    # Only 'documented' reasons are resampled — the one 'harvested' entry
    # (payment_failed, the real Day 1 observation) is a specific literal fact, not a
    # generic reason available for synthetic rows to draw. Sampling it here would
    # mislabel synthesized rows decline_class_source='harvested' when they're not —
    # caught by test_harvested_row_passes_through_untouched actually failing.
    reasons = [
        r for r, info in REASON_TAXONOMY.items()
        if info.decline_class == decline_class and info.source == "documented"
    ]
    if not reasons:
        raise ValueError(f"no documented reasons classified {decline_class!r}")
    return reasons


def build_corpus(
    n: int,
    seed: int,
    batch_simulated_start_at: datetime,
    soft_share: float = 0.80,  # docs/assumptions.md: soft_decline_share
    hard_share_of_nonsoft: float = 0.5,  # docs/assumptions.md: hard_share_of_nonsoft
    ticket_size_median_paise: int = 80_000,  # docs/assumptions.md: ticket_size_lognormal_median_paise
    ticket_size_sigma: float = 1.2,  # docs/assumptions.md: ticket_size_lognormal_sigma
    arrival_window_days: int = 30,  # docs/assumptions.md: arrival_window_days
    card_reuse_factor: float = 4.0,  # docs/assumptions.md: card_reuse_factor
) -> list[CaseDraft]:
    rng = random.Random(seed)

    n_cards = max(1, round(n / card_reuse_factor))
    card_pool = [f"card_synth_{_rand_hex(rng)}" for _ in range(n_cards)]

    drafts: list[CaseDraft] = []
    for _ in range(n):
        if rng.random() < soft_share:
            decline_class = SOFT
        else:
            decline_class = HARD if rng.random() < hard_share_of_nonsoft else TECHNICAL

        reason = rng.choice(_reasons_for_class(decline_class))
        info = REASON_TAXONOMY[reason]

        # Log-normal ticket size, floored at ₹1 (100 paise) — a payment of literally
        # zero or negative paise isn't a real case.
        amount = max(100, round(math.exp(rng.gauss(math.log(ticket_size_median_paise), ticket_size_sigma))))

        simulated_at = batch_simulated_start_at + timedelta(days=rng.uniform(0, arrival_window_days))

        drafts.append(CaseDraft(
            razorpay_payment_id=f"pay_synth_{_rand_hex(rng)}",
            razorpay_order_id=f"order_synth_{_rand_hex(rng)}",
            card_id=rng.choice(card_pool),
            amount=amount,
            currency="INR",
            # Razorpay's card error-codes reference publishes the reason string and a
            # plain-language description only — no error_code/source/step alongside
            # any of the 16 entries (see docs/assumptions.md). Rather than assert an
            # unverified code/source/step mapping after already catching one
            # fabricated citation this session, synthesized rows leave these None:
            # decline_class_source='documented' already flags that this row's fields
            # beyond error_reason itself aren't independently confirmed.
            error_code=None,
            error_reason=reason,
            error_description=None,
            error_source=None,
            error_step=None,
            decline_class=info.decline_class,
            decline_class_source=info.source,
            risk_flagged=info.risk_flagged,
            simulated_at=simulated_at,
        ))

    for p in _load_harvested_failures():
        info = classify(p["error_code"], p["error_reason"])
        drafts.append(CaseDraft(
            razorpay_payment_id=p["id"],
            razorpay_order_id=p["order_id"],
            card_id=p["card_id"],
            amount=p["amount"],
            currency=p["currency"],
            error_code=p["error_code"],
            error_reason=p["error_reason"],
            error_description=p["error_description"],
            error_source=p["error_source"],
            error_step=p["error_step"],
            decline_class=info.decline_class,
            decline_class_source=info.source,
            risk_flagged=info.risk_flagged,
            simulated_at=batch_simulated_start_at,
        ))

    return drafts
