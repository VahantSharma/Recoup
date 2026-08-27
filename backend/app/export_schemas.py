"""Pydantic models for every artifact Recoup exports to the frontend. Day 5's standing
rule, enforced here structurally rather than by convention: no number reaches the
screen except through a committed artifact, and no artifact reaches disk except as an
instance of one of these models -- app.export.write_artifact() takes a model instance,
never a raw dict, so a script can't emit a malformed artifact even by accident.

Each artifact carries its own ArtifactManifest (git SHA, seed, corpus hash, simulator
params, CRN flag, timestamp) -- CLAUDE.md's "every number resolves to a manifest" made
literal, per docs/day5surfaceplan.md's architecture decision.

Built today: CaseAuditArtifact only (Stage 2's one vertical slice). The other five
artifacts named in docs/day5surfaceplan.md's Stage 1 get their own model classes here
when their own screens are built, not before:
  - day3_ablation      (Stage 3 — ablation table + sliders)
  - day3_sweep         (Stage 3 — sensitivity sweep)
  - day4_bakeoff       (Stage 5 — model layer panel)
  - day4_held_out_ablation  (Stage 4 — portfolio view)
  - day4_bound_decomposition (Stage 4 — portfolio view, three-bound decomposition)
"""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict


class ArtifactManifest(BaseModel):
    """Embedded verbatim in every artifact. seed is an int for a single-seed run, or a
    dict ({"master_seed": ..., "held_out_seeds": [...]}) for a multi-seed one -- kept
    as one field rather than two so a script can't populate the wrong one."""

    model_config = ConfigDict(extra="forbid")

    git_sha: str
    script: str  # e.g. "scripts/export_case_audit.py"
    schema_name: str
    schema_version: str
    generated_at: datetime  # wall clock -- distinct from any simulated date inside data
    seed: int | dict
    corpus_hash: str | None
    policy_params: dict
    simulator_params: dict
    use_common_random_numbers: bool


class GuardrailVerdictRow(BaseModel):
    """One row of one gate call's guardrail table -- see app.gate.GUARDRAIL_ORDER,
    imported and walked, never re-declared here."""

    model_config = ConfigDict(extra="forbid")

    name: str  # one of app.gate.GUARDRAIL_ORDER's 9 entries (incl. "permitted")
    evaluated: bool  # False iff short-circuited before this guardrail was ever reached
    fired: bool  # True for at most one row per gate call
    note: str  # "" | "not evaluated -- short-circuited at <name>"


class GateCallRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_number: int
    at: datetime  # the harness's simulated clock, not wall clock
    proposal_action_type: str
    proposal_amount_paise: int | None
    decision: str  # "approved" | "rejected"
    reason: str  # the fired guardrail's name, or "permitted"
    route_to: str | None
    idempotency_key: str  # app.state_machine.derive_idempotency_key(case_id, attempt_number)
    guardrail_table: list[GuardrailVerdictRow]


class CaseAuditRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str  # a real razorpay_payment_id, or "crafted-<guardrail-name>"
    case_kind: str  # "corpus" | "crafted"
    crafted_note: str | None  # populated iff case_kind == "crafted"
    decline_class: str
    decline_class_source: str  # "harvested" | "documented"
    error_code: str | None
    error_reason: str | None
    error_description: str | None
    amount_paise: int
    gate_calls: list[GateCallRow]
    final_status: str
    route_to: str | None
    outcome: str  # "recovered" | "deferred_to_human_review" | "not_recovered"


class UnreachableGuardrailNote(BaseModel):
    """For the guardrails no case in this artifact can represent -- stale_reconcile and
    already_resolved are properties of the harness itself (see docs/results.md), not a
    per-case condition, so a crafted case pretending otherwise would misrepresent it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    why: str


class CaseAuditArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "case_audit"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    default_case_id: str  # pay_TSv8WoMc4OAEGG — the real harvested Day 1 payment
    cases: list[CaseAuditRow]
    structurally_unreachable_guardrails: list[UnreachableGuardrailNote]
