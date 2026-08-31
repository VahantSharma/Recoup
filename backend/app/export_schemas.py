"""Pydantic models for every artifact Recoup exports to the frontend. The standing
rule, enforced here structurally rather than by convention: no number reaches the
screen except through a committed artifact, and no artifact reaches disk except as an
instance of one of these models -- app.export.write_artifact() takes a model instance,
never a raw dict, so a script can't emit a malformed artifact even by accident.

Each artifact carries its own ArtifactManifest (git SHA, seed, corpus hash, simulator
params, CRN flag, timestamp) -- docs/ENGINEERING-DOCTRINE.md's "every number resolves
to a manifest" made literal.

Built through Stage 3: CaseAuditArtifact (Stage 2) and the five Stage-3 artifacts below
— day3_ablation, day3_sweep, day4_held_out_ablation, day4_bound_decomposition,
day4_bakeoff. Every field mirrors a value the underlying script already computes and
prints; nothing here is a new computation invented for the frontend's sake.
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


# ============================================================================
# Stage 3 — day3_ablation: the checkpoint ablation (control/blind_retry/rules_only,
# n=1200/1201, one seed), guardrail reachability, and compliance economics. See
# scripts/run_day3_ablation.py, which this artifact's build step reads results from
# directly -- no field here is a new computation.
# ============================================================================


class ArmOutcomeRow(BaseModel):
    """One arm's three-way outcome split plus attempts/violations/amounts -- gross
    recovery and its violation count live in the SAME row on purpose, never a separate
    table, so blind-retry's higher gross recovery can never be shown without what it
    costs sitting right next to it."""

    model_config = ConfigDict(extra="forbid")

    arm: str
    recovered_rate: float
    deferred_rate: float
    not_recovered_rate: float
    total_attempts: int
    total_violations: int
    recovered_amount_paise: int
    deferred_amount_paise: int
    net_value_paise: float


class PairedLiftRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm_a: str
    arm_b: str  # lift is A minus B
    n_cases: int
    rate_a: float
    rate_b: float
    rate_lift: float
    rate_lift_ci_low: float
    rate_lift_ci_high: float
    amount_lift_paise: int
    amount_lift_ci_low_paise: float
    amount_lift_ci_high_paise: float


class GuardrailReachabilityRow(BaseModel):
    """One row of app.gate.GUARDRAIL_ORDER's real firing counts against this run, plus
    the reachability verdict app.harness reasoning already establishes -- see
    scripts/run_day3_ablation.py's own REACHABILITY dict, reused verbatim, never
    re-derived here."""

    model_config = ConfigDict(extra="forbid")

    name: str  # one of GUARDRAIL_ORDER's 9 entries, including "permitted"
    count: int
    share: float
    reachable: bool | None  # null for "permitted" -- it isn't a guardrail
    why: str  # "" for "permitted"


class ComplianceEconomics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    net_value_blind_retry_paise: float
    net_value_rules_only_paise: float
    violations_blind_retry: int
    break_even_penalty_paise: float
    break_even_penalty_usd: float
    usd_to_inr: float
    visa_penalty_paise: float
    mastercard_low_paise: float
    mastercard_high_paise: float


class Day3AblationArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "day3_ablation"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    n: int
    master_seed: int
    arms: list[ArmOutcomeRow]
    lifts: list[PairedLiftRow]
    guardrail_reachability: list[GuardrailReachabilityRow]
    compliance: ComplianceEconomics


# ============================================================================
# Stage 3 — day3_sweep: the OAT grid (5 real computed points per declared parameter)
# and the joint-random summary. THE ONE RULE: a slider built on this artifact must
# only ever snap to one of `points` -- there is no value between two computed points,
# and nothing here is meant to be interpolated. See scripts/run_day3_sweep.py and
# app/harness/sweep.py's PARAM_SPECS, which this artifact's own `lo`/`hi`/`default`
# per parameter are read from directly, not re-typed.
# ============================================================================


class OATPoint(BaseModel):
    """One real, computed grid point -- never an interpolated value. `value` is this
    point's actual parameter setting; every other field is that parameter's real,
    measured effect on the ablation at this exact setting, everything else held at its
    own default."""

    model_config = ConfigDict(extra="forbid")

    value: float
    rate_control: float
    rate_rules_only: float
    rate_blind_retry: float
    rate_lift_rules_vs_control: float
    rules_beats_control: bool
    rate_lift_blind_vs_rules: float
    blind_beats_rules: bool
    break_even_penalty_paise: float | None


class OATParameterSweep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    lo: float
    hi: float
    default: float
    points: list[OATPoint]  # exactly 5: lo, 25%, default, 75%, hi -- see oat_sweep()
    lift_spread: float  # max(rate_lift_rules_vs_control) - min(...) across points


class JointSweepSummary(BaseModel):
    """The 500-draw joint-random sweep, summarized -- not a per-draw grid a slider
    could snap to (each draw varies all 15 parameters at once, so there is no single
    axis to place it on). Reported for the compliance-economics distribution and the
    ranking-survival count, matching docs/results.md's own framing exactly."""

    model_config = ConfigDict(extra="forbid")

    n_draws: int
    n_cases_per_draw: int
    rules_beats_control_count: int  # out of n_draws -- the near-tautological sanity check
    n_draws_with_break_even: int  # excludes draws where blind_retry made 0 violations
    break_even_p5_paise: float
    break_even_p50_paise: float
    break_even_p95_paise: float
    fraction_below_visa: float
    fraction_below_mastercard_low: float
    fraction_below_mastercard_high: float
    visa_penalty_paise: float
    mastercard_low_paise: float
    mastercard_high_paise: float


class Day3SweepArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "day3_sweep"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    oat_n: int  # cases per OAT point
    base_seed: int
    parameters: list[OATParameterSweep]  # 15 declared parameters, PARAM_SPECS order
    most_consequential: list[str]  # parameter names, sorted by lift_spread descending —
                                     # the top two are the disclosed near-tie
    joint: JointSweepSummary


# ============================================================================
# Stage 3 — day4_held_out_ablation: all 8 arms (6 submittable, 2 analysis-only) across
# the 10 held-out seeds. See scripts/run_day4_ablation.py.
# ============================================================================


class LiftDistribution(BaseModel):
    """A model-sourced or reference arm's rate lift vs. rules_only, across the 10
    held-out seeds -- mean/stdev/min/max plus how many of the 10 were positive, exactly
    the distribution scripts/run_day4_ablation.py prints per arm."""

    model_config = ConfigDict(extra="forbid")

    mean: float
    stdev: float
    min: float
    max: float
    positive_seeds: int
    total_seeds: int


class ArmHeldOutRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arm: str
    is_shippable: bool  # False for observable_optimal, oracle_upper_bound -- these are
                          # never candidates to ship, and the screen must never let a
                          # reader mistake one for a policy this project could deploy
    mean_recovery_rate: float  # averaged across the 10 held-out seeds
    total_violations: int  # summed across all 10 seeds -- 0 for every arm except
                             # blind_retry, by construction (every other arm is enforced)
    lift_vs_rules_only: LiftDistribution | None  # null for control/blind_retry/rules_only
                                                    # itself -- the script only computes
                                                    # this for MODEL_SOURCED_ARMS + REFERENCE_ARMS
    total_yields: int | None  # null for arms with no yield-at-scarcity mechanism at all


class Day4HeldOutAblationArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "day4_held_out_ablation"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    held_out_seeds: list[int]
    n_per_seed: int
    arms: list[ArmHeldOutRow]  # 8 rows, in ALL_ARMS order
    modal_ranking: list[str]  # descending by absolute recovery rate
    modal_ranking_hold_count: int  # out of len(held_out_seeds)
    per_seed_rankings: list[list[str]]  # one ranking per held-out seed, same order as held_out_seeds


# ============================================================================
# Stage 3 — day4_bound_decomposition: the three-bound decomposition, both metrics
# (rate and net value), since they disagree and that disagreement is the finding. See
# scripts/run_bound_decomposition.py.
# ============================================================================


class RateBySeedRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    rules_only: float
    observable_optimal: float
    oracle_upper_bound: float
    oracle_value_maximizing: float


class NetValueBySeedRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    rules_only_paise: float
    observable_optimal_paise: float
    oracle_upper_bound_paise: float
    oracle_value_maximizing_paise: float


class GapStat(BaseModel):
    """One gap in one metric, in-sample plus its held-out distribution -- e.g.
    'observable_optimal - rules_only' on recovery rate. `positive_at`/`total_points`
    covers all 11 points (PROPOSAL_SEED + the 10 held-out seeds)."""

    model_config = ConfigDict(extra="forbid")

    label: str
    in_sample: float
    held_out_mean: float
    held_out_stdev: float
    held_out_min: float
    held_out_max: float
    positive_at: int
    total_points: int


class Day4BoundDecompositionArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "day4_bound_decomposition"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    proposal_seed: int
    held_out_seeds: list[int]
    rate_by_seed: list[RateBySeedRow]  # 11 rows: proposal_seed first, then held-out
    net_value_by_seed_paise: list[NetValueBySeedRow]  # 11 rows, same order

    # RATE — primary chain: rules_only -> observable_optimal -> oracle_upper_bound
    rate_gap1: GapStat  # observable_optimal - rules_only
    rate_gap2: GapStat  # oracle_upper_bound - observable_optimal

    # NET VALUE — primary chain: rules_only -> observable_optimal -> oracle_value_maximizing
    net_value_gap1_paise: GapStat  # observable_optimal - rules_only
    net_value_gap2_paise: GapStat  # oracle_value_maximizing - observable_optimal

    dominance_check_holds_at_every_seed: bool  # oracle_value_maximizing >= oracle_upper_bound, net value
    dominance_check_failed_seeds: list[int]

    attempts_conserved_net: int  # rules_only's total attempts minus oracle_upper_bound's, PROPOSAL_SEED
    attempts_reduced_by_class: dict[str, int]
    attempts_increased_by_class: dict[str, int]

    overfitting_gap_paise: float  # observable_optimal's in-sample net-value LIFT vs rules_only,
                                    # minus its held-out mean lift -- never an absolute cross-seed figure


# ============================================================================
# Stage 3 — day4_bakeoff: the real 20-call/provider bake-off, the three pre-registered
# abstention checks with their computed values, and which one fired. See
# scripts/run_day4_bakeoff.py and app/model/abstention.py.
# ============================================================================


class AbstentionCheckRow(BaseModel):
    """One of the pre-registered rule's checks, with the actual number it computed
    against the actual threshold -- never just the pass/fail bit on its own."""

    model_config = ConfigDict(extra="forbid")

    rule: str  # "A" | "B_weight_ratio" | "B_defer_priority_cutoff" | "C"
    description: str
    computed_value: str  # e.g. "1.265" or "60.0%" -- pre-formatted, since the checks mix CVs and fractions
    threshold: str  # e.g. "<= 0.30" or ">= 60%"
    fired: bool


class ProviderBakeoffResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model_id: str
    n_calls: int
    schema_valid_count: int
    sensible_count: int
    abstained: bool
    abstain_reason: str | None
    checks: list[AbstentionCheckRow]
    total_input_tokens: int
    total_output_tokens: int


class Day4BakeoffArtifact(BaseModel):
    SCHEMA_NAME: ClassVar[str] = "day4_bakeoff"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = ConfigDict(extra="forbid")

    proposal_seed: int
    n_calls_per_provider: int
    abstention_rule_commit_sha: str  # the commit that added app/model/abstention.py
    abstention_rule_commit_date: str  # ISO date -- shown alongside the SHA so "before
                                        # any result existed" is a checkable date compare,
                                        # not just an assertion
    bakeoff_commit_sha: str  # the commit that ran the real 20-call/provider bake-off
    bakeoff_commit_date: str  # ISO date -- compared against abstention_rule_commit_date
                                # directly, so "predates" is a checkable fact, not an assertion
    providers: list[ProviderBakeoffResult]
