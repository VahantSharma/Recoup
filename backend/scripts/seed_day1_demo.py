"""Day 1 demo: intake the real harvested failure into the case store.

Not a fabricated row — pay_TSv8WoMc4OAEGG is a real payment, driven through Razorpay's
actual test-mode checkout this session (see backend/data/harvested_corpus.json).

Deliberately stops at ELIGIBLE. The plan originally said "show a payment_cases row +
its first case_attempts row" — but the policy gate (Day 2) doesn't exist yet, so there
is no real gate decision or reconcile-before-act to attach to a case_attempts row yet.
Inserting one anyway would be exactly the kind of fabricated state CLAUDE.md forbids.
The case_attempts mechanism itself (idempotency-key derivation, uniqueness, replay-is-
a-no-op) is proven instead by backend/tests/test_idempotency.py.

Run: cd backend && python -m scripts.seed_day1_demo
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.db import SessionLocal, init_db
from app.intake import assign_arms_stratified
from app.models import Batch, PaymentCase
from app.state_machine import transition
from app.taxonomy import classify

CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "harvested_corpus.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def main() -> None:
    init_db()
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    failed = [e for e in corpus["entries"] if e["payment"]["status"] == "failed"]

    infos = [classify(e["payment"]["error_code"], e["payment"]["error_reason"]) for e in failed]
    arms = assign_arms_stratified([i.decline_class for i in infos], seed=42)

    session = SessionLocal()
    try:
        batch = Batch(seed=42, description="Day 1 demo — real harvested corpus, 2026-08-22")
        session.add(batch)
        session.flush()

        inserted = []
        for entry, info, arm in zip(failed, infos, arms):
            p = entry["payment"]
            case = PaymentCase(
                batch_id=batch.id,
                razorpay_payment_id=p["id"],
                razorpay_order_id=p["order_id"],
                card_id=p["card_id"],  # token only — no network/last4, per policy
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
                arm=arm,
                state="INTAKE",
            )
            session.add(case)
            session.flush()
            transition(case, "CLASSIFIED", now=_now)
            transition(case, "ELIGIBLE", now=_now)
            inserted.append(case)

        session.commit()
        for case in inserted:
            session.refresh(case)
            print(
                f"Inserted {case.id}: razorpay_payment_id={case.razorpay_payment_id} "
                f"decline_class={case.decline_class} ({case.decline_class_source}) "
                f"arm={case.arm} state={case.state}"
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
