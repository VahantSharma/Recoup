"""Day 5's one live path (docs/day5surfaceplan.md): a single FastAPI endpoint that
performs reconcile-before-act against real Razorpay test mode on the one real harvested
payment, and demonstrates that a replayed action with the same idempotency key is a
no-op. Everything else in the surface layer reads committed artifacts (app.export); this
is the deliberate exception, and the only one.

Built last, after the static case audit screen renders correctly -- per the approved
plan's timebox, a network path never entangles the first screen's debugging.

Two things a demo of "reconcile-before-act" must both do to be a proof and not just a
claim (round 2 of plan review):
  1. Reconcile must actually GATE the action, not just precede it -- if the reconciled
     status shows the payment already resolved elsewhere, the gate refuses, and no
     Payment Link is created. simulate_resolved_elsewhere lets a judge see that branch
     live (the real payment stays 'failed' forever in test mode, so it could otherwise
     never be observed) -- the override is always disclosed in the response, never silent.
  2. attempt_number is a request parameter, not hardcoded -- so both the fresh-action
     path and the replay-is-a-no-op path are reproducible on demand, forever, no DB
     surgery between demo runs.

Run: cd backend && uvicorn app.main:app --reload
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from . import gate
from .db import SessionLocal, init_db
from .gate import ActionProposal
from .models import Batch, CaseAttempt, PaymentCase
from .state_machine import derive_idempotency_key, transition
from .taxonomy import classify

load_dotenv()  # same pattern as app/model/provider.py -- repo-root .env, harmless if absent

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
RAZORPAY_API_BASE = "https://api.razorpay.com/v1"

# The one live target -- pay_TSv8WoMc4OAEGG, the real Day 1 harvested payment (see
# backend/data/harvested_corpus.json). Hardcoded on purpose: this is a single
# demonstration endpoint, not a general-purpose retry API.
LIVE_CASE_RAZORPAY_PAYMENT_ID = "pay_TSv8WoMc4OAEGG"
LIVE_CASE_ORDER_ID = "order_TSv7T8tZA1itmS"
LIVE_CASE_AMOUNT_PAISE = 10_000
LIVE_CASE_CURRENCY = "INR"
LIVE_CASE_ERROR_CODE = "BAD_REQUEST_ERROR"
LIVE_CASE_ERROR_REASON = "payment_failed"
LIVE_CASE_ERROR_DESCRIPTION = "Payment failed"

# What simulate_resolved_elsewhere forces the reconciled status to, for demo purposes
# only -- 'captured' is in app.gate._RESOLVED_STATUSES, so this reliably trips
# already_resolved without needing the ability to actually mutate Razorpay's real
# record of a already-failed test-mode payment (which the API doesn't allow anyway).
RESOLVED_ELSEWHERE_DEMO_STATUS = "captured"

app = FastAPI(title="Recoup -- live verification endpoint")

# The case audit screen (frontend/) calls this endpoint directly from the browser, on
# whatever port `npm run dev`/`vite preview` picked -- a local demonstration instrument
# a judge runs on their own machine, not a deployed public service, so a fixed allowlist
# of the common local dev ports is the right amount of caution: permissive enough that
# the demo isn't fragile to which port Vite happened to pick, without being a bare "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",  # vite dev default
        "http://localhost:4173", "http://127.0.0.1:4173",  # vite preview default
        "http://localhost:5174", "http://127.0.0.1:5174",  # vite dev, port already taken
        "http://localhost:5175", "http://127.0.0.1:5175",
        "http://localhost:5176", "http://127.0.0.1:5176",
    ],
    allow_methods=["POST", "OPTIONS"],  # OPTIONS explicit: the browser's own preflight,
                                          # not something a caller ever sends deliberately
    allow_headers=["*"],
)


class LiveActionResponse(BaseModel):
    case_id: str
    razorpay_payment_id: str
    attempt_number: int
    reconciled_status_real: str
    reconciled_status_used: str
    reconcile_overridden: bool
    gate_decision: str
    gate_reason: str
    action_taken: str  # "created" | "replayed_no_op" | "refused"
    idempotency_key: str | None
    payment_link_short_url: str | None


def _find_or_create_live_case(session) -> PaymentCase:
    """Find-or-create, never insert-unconditionally -- calling this endpoint twice must
    resolve to the SAME case row, or the idempotency proof below would be checking the
    wrong key on the second call. Mirrors scripts/seed_day1_demo.py's own construction
    of this exact case (same razorpay_payment_id, same classify() call)."""
    existing = session.execute(
        select(PaymentCase)
        .where(PaymentCase.razorpay_payment_id == LIVE_CASE_RAZORPAY_PAYMENT_ID)
        .order_by(PaymentCase.created_at.asc())
        .limit(1)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    info = classify(LIVE_CASE_ERROR_CODE, LIVE_CASE_ERROR_REASON)
    batch = Batch(seed=42, description="Day 5 live endpoint -- case store row for the harvested payment")
    session.add(batch)
    session.flush()
    case = PaymentCase(
        batch_id=batch.id, razorpay_payment_id=LIVE_CASE_RAZORPAY_PAYMENT_ID,
        razorpay_order_id=LIVE_CASE_ORDER_ID, card_id=None,
        amount=LIVE_CASE_AMOUNT_PAISE, currency=LIVE_CASE_CURRENCY,
        error_code=LIVE_CASE_ERROR_CODE, error_reason=LIVE_CASE_ERROR_REASON,
        error_description=LIVE_CASE_ERROR_DESCRIPTION, error_source=None, error_step=None,
        decline_class=info.decline_class, decline_class_source=info.source,
        risk_flagged=info.risk_flagged, arm="rules_only", state="INTAKE",
    )
    session.add(case)
    session.flush()
    _now = lambda: datetime.now(timezone.utc)  # noqa: E731 -- matches transition()'s injected-clock signature
    transition(case, "CLASSIFIED", now=_now)
    transition(case, "ELIGIBLE", now=_now)
    session.commit()
    session.refresh(case)
    return case


async def _reconcile_live(client: httpx.AsyncClient) -> str:
    """The real reconcile-before-act call CLAUDE.md requires, run live, immediately
    before the gate is ever consulted."""
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(500, "RAZORPAY_KEY_ID/RAZORPAY_KEY_SECRET not set -- see SETUP.md")
    resp = await client.get(
        f"{RAZORPAY_API_BASE}/payments/{LIVE_CASE_RAZORPAY_PAYMENT_ID}",
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
    )
    resp.raise_for_status()
    return resp.json()["status"]


async def _create_payment_link(client: httpx.AsyncClient, case: PaymentCase) -> str:
    """The actual retry_payment_link action the harness models -- a real, free
    test-mode Payment Link, never a live charge."""
    resp = await client.post(
        f"{RAZORPAY_API_BASE}/payment_links",
        auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
        json={
            "amount": case.amount,
            "currency": case.currency,
            "description": f"Recoup recovery retry -- case {case.id}",
            "notes": {"recoup_case_id": case.id, "recoup_source": "day5-live-endpoint-demo"},
        },
    )
    resp.raise_for_status()
    return resp.json()["short_url"]


@app.post("/api/live/verify-recovery-action", response_model=LiveActionResponse)
async def verify_recovery_action(
    attempt_number: int = Query(
        ..., ge=1,
        description="This case's attempt sequence number. Call the same value twice to "
                     "see the replay no-op; increment it to see a fresh action again.",
    ),
    simulate_resolved_elsewhere: bool = Query(
        False,
        description="Demo-only: forces the status fed to the gate to 'captured'. The "
                     "real fetched status is always reported too, alongside this flag.",
    ),
) -> LiveActionResponse:
    init_db()
    session = SessionLocal()
    try:
        case = _find_or_create_live_case(session)

        async with httpx.AsyncClient(timeout=15.0) as client:
            reconciled_status_real = await _reconcile_live(client)
            reconciled_at = datetime.now(timezone.utc)
            reconciled_status_used = (
                RESOLVED_ELSEWHERE_DEMO_STATUS if simulate_resolved_elsewhere else reconciled_status_real
            )

            window_start = reconciled_at - timedelta(days=30)
            attempt_count_in_window = session.execute(
                select(func.count())
                .select_from(CaseAttempt)
                .where(CaseAttempt.case_id == case.id, CaseAttempt.created_at >= window_start)
            ).scalar_one()

            # The actual, unmodified gate function -- reconcile is load-bearing here,
            # not decorative: a resolved-elsewhere status genuinely changes result.decision.
            result = gate.evaluate(
                case,
                ActionProposal(action_type="retry_payment_link", amount_paise=case.amount),
                reconciled_payment={"status": reconciled_status_used},
                reconciled_at=reconciled_at,
                attempt_count_in_window=attempt_count_in_window,
                now=reconciled_at,
            )

            if result.decision != gate.APPROVED:
                return LiveActionResponse(
                    case_id=case.id, razorpay_payment_id=case.razorpay_payment_id,
                    attempt_number=attempt_number, reconciled_status_real=reconciled_status_real,
                    reconciled_status_used=reconciled_status_used,
                    reconcile_overridden=simulate_resolved_elsewhere,
                    gate_decision=result.decision, gate_reason=result.reason,
                    action_taken="refused", idempotency_key=None, payment_link_short_url=None,
                )

            idempotency_key = derive_idempotency_key(case.id, attempt_number)
            attempt = CaseAttempt(
                case_id=case.id, attempt_number=attempt_number, idempotency_key=idempotency_key,
                action_type="retry_payment_link", reconciled_state=reconciled_status_real,
                reconciled_at=reconciled_at, gate_decision=result.decision, gate_reason=result.reason,
                decline_class_source_at_decision=case.decline_class_source,
            )
            session.add(attempt)
            try:
                session.commit()
            except IntegrityError:
                # The idempotency proof: a replayed (case_id, attempt_number) hits the
                # UNIQUE constraint -- caught here, never a second Payment Link created.
                session.rollback()
                existing = session.execute(
                    select(CaseAttempt).where(
                        CaseAttempt.case_id == case.id, CaseAttempt.attempt_number == attempt_number,
                    )
                ).scalar_one()
                return LiveActionResponse(
                    case_id=case.id, razorpay_payment_id=case.razorpay_payment_id,
                    attempt_number=attempt_number, reconciled_status_real=reconciled_status_real,
                    reconciled_status_used=reconciled_status_used,
                    reconcile_overridden=simulate_resolved_elsewhere,
                    gate_decision=result.decision, gate_reason=result.reason,
                    action_taken="replayed_no_op", idempotency_key=existing.idempotency_key,
                    payment_link_short_url=None,
                )

            short_url = await _create_payment_link(client, case)
            attempt.executed_at = datetime.now(timezone.utc)
            session.commit()

            return LiveActionResponse(
                case_id=case.id, razorpay_payment_id=case.razorpay_payment_id,
                attempt_number=attempt_number, reconciled_status_real=reconciled_status_real,
                reconciled_status_used=reconciled_status_used,
                reconcile_overridden=simulate_resolved_elsewhere,
                gate_decision=result.decision, gate_reason=result.reason,
                action_taken="created", idempotency_key=idempotency_key,
                payment_link_short_url=short_url,
            )
    finally:
        session.close()
