"""Pydantic v2 read schemas — the API-facing boundary, kept deliberately separate from
app.models (see db.py's module docstring for why)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    case_id: str
    attempt_number: int
    idempotency_key: str
    action_type: str
    scheduled_for: datetime | None
    reconciled_state: str | None
    reconciled_at: datetime | None
    gate_decision: str | None
    gate_reason: str | None
    executed_at: datetime | None
    outcome: str | None
    created_at: datetime


class CaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    batch_id: str
    razorpay_payment_id: str
    razorpay_order_id: str | None
    card_id: str | None
    amount: int
    currency: str
    error_code: str | None
    error_reason: str | None
    error_description: str | None
    error_source: str | None
    error_step: str | None
    decline_class: str
    decline_class_source: str
    risk_flagged: bool
    arm: str
    state: str
    excluded_reason: str | None
    state_updated_at: datetime
    created_at: datetime
    attempts: list[AttemptRead] = []
