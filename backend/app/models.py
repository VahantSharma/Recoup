"""SQLAlchemy 2.0 models for the durable case store.

Three tables. Separating **case** (identity + classification + current state) from
**attempt** (one row per money-touching action, carrying its own idempotency key) is
the load-bearing decision — it's what makes "idempotency key per attempt" concrete
instead of aspirational, and what makes "process dies mid-action, resumes instead of
re-firing" a query (`WHERE idempotency_key = ?`) instead of a hope.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


class Batch(Base):
    """One eval-harness run / intake batch. `seed` makes arm assignment reproducible —
    the same seed always produces the same stratified arm assignment for the same
    input cases (see app.intake.assign_arms_stratified)."""

    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: _new_id("batch"))
    seed: Mapped[int]
    description: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)

    # Run provenance (Day 2) — the DATABASE_URL bug's lesson made structural: a stale
    # corpus, a changed seed, or an uncommitted policy tweak between two runs must
    # never be invisible. See app.manifest.
    git_sha: Mapped[str] = mapped_column(default="unknown")
    db_path: Mapped[str] = mapped_column(default="unknown")  # snapshotted, not trusted
                                                               # to stay stable globally
    corpus_hash: Mapped[str] = mapped_column(default="unknown")
    params_json: Mapped[str] = mapped_column(default="{}")
    simulated_start_at: Mapped[datetime] = mapped_column(default=_now)  # this batch's
                                                                          # simulated "day 0"

    cases: Mapped[list["PaymentCase"]] = relationship(back_populates="batch")


class PaymentCase(Base):
    __tablename__ = "payment_cases"

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: _new_id("case"))
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"))

    razorpay_payment_id: Mapped[str]
    razorpay_order_id: Mapped[str | None] = mapped_column(default=None)
    # Razorpay's card_xxx token only — no network, no last4. Strict reading of
    # CLAUDE.md's "No card data — tokenized references only," confirmed with the user.
    card_id: Mapped[str | None] = mapped_column(default=None)

    amount: Mapped[int]  # paise
    currency: Mapped[str] = mapped_column(default="INR")

    # Razorpay's own error fields, verbatim — error_description is raw narration text,
    # the model's input, never a guardrail's.
    error_code: Mapped[str | None] = mapped_column(default=None)
    error_reason: Mapped[str | None] = mapped_column(default=None)
    error_description: Mapped[str | None] = mapped_column(default=None)
    error_source: Mapped[str | None] = mapped_column(default=None)
    error_step: Mapped[str | None] = mapped_column(default=None)

    decline_class: Mapped[str]  # hard | soft | technical | none (none = not a failure)
    # 'harvested' = observed on a real API response this session; 'documented' =
    # sourced from Razorpay's public reference docs, not reproduced live. Test mode's
    # mock bank page turned out not to branch on card number — only two outcomes are
    # actually harvestable (success, and one generic gateway decline) — see
    # recoup-razorpay-error-taxonomy-doc-sourced memory. Keeping this column honest is
    # a direct instance of CLAUDE.md's "what's real vs. simulated" principle.
    decline_class_source: Mapped[str]
    risk_flagged: Mapped[bool] = mapped_column(default=False)

    arm: Mapped[str]  # control | blind_retry | rules_only | rules_plus_model
    state: Mapped[str] = mapped_column(default="INTAKE")
    excluded_reason: Mapped[str | None] = mapped_column(default=None)

    state_updated_at: Mapped[datetime] = mapped_column(default=_now)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    # Simulated arrival time within the batch's simulated window (distinct from
    # created_at, the real wall-clock DB insert time) — see docs/assumptions.md's
    # Time model. The gate's `now` is always this clock, never wall-clock.
    simulated_at: Mapped[datetime] = mapped_column(default=_now)

    batch: Mapped["Batch"] = relationship(back_populates="cases")
    attempts: Mapped[list["CaseAttempt"]] = relationship(
        back_populates="case", order_by="CaseAttempt.attempt_number"
    )


class CaseAttempt(Base):
    """One row per money-touching action. `idempotency_key` is derived deterministically
    from (case_id, attempt_number) — see app.state_machine.derive_idempotency_key — and
    is UNIQUE, so inserting a replayed attempt is a constraint violation the caller
    must catch and treat as a no-op, not a second action. Razorpay's own idempotency
    headers (X-Payout/Refund/Transfer-Idempotency) don't cover Orders/Payment Links, so
    this table is the entire enforcement mechanism — not a convenience on top of one
    Razorpay provides."""

    __tablename__ = "case_attempts"
    __table_args__ = (
        UniqueConstraint("case_id", "attempt_number", name="uq_case_attempt_number"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=lambda: _new_id("attempt"))
    case_id: Mapped[str] = mapped_column(ForeignKey("payment_cases.id"))
    attempt_number: Mapped[int]
    idempotency_key: Mapped[str] = mapped_column(unique=True)

    action_type: Mapped[str]  # retry_payment_link | no_action | escalate_human
    scheduled_for: Mapped[datetime | None] = mapped_column(default=None)

    # Proof reconcile-before-act actually ran, not just a claim — the live Razorpay
    # state fetched immediately before acting.
    reconciled_state: Mapped[str | None] = mapped_column(default=None)
    reconciled_at: Mapped[datetime | None] = mapped_column(default=None)

    gate_decision: Mapped[str | None] = mapped_column(default=None)  # approved | rejected
    gate_reason: Mapped[str | None] = mapped_column(default=None)

    executed_at: Mapped[datetime | None] = mapped_column(default=None)
    outcome: Mapped[str | None] = mapped_column(default=None)  # recovered | still_failed | error

    # Denormalized copy of case.decline_class_source at the moment this decision was
    # recorded — on purpose, so an audit-log row is self-contained (whether THIS
    # decision rested on live or documented evidence) without depending on a join to
    # still resolve correctly years later, even if the case row's classification is
    # ever revised.
    decline_class_source_at_decision: Mapped[str | None] = mapped_column(default=None)

    created_at: Mapped[datetime] = mapped_column(default=_now)

    case: Mapped["PaymentCase"] = relationship(back_populates="attempts")
