// Hand-written TS interfaces mirroring backend/app/export_schemas.py's Pydantic
// models. Small, stable set today (case_audit only) -- kept in sync by hand until
// there's enough artifact churn to justify generating these.

export interface ArtifactManifest {
  git_sha: string;
  script: string;
  schema_name: string;
  schema_version: string;
  generated_at: string; // ISO 8601, wall clock
  seed: number | { master_seed: number; held_out_seeds: number[] };
  corpus_hash: string | null;
  policy_params: Record<string, unknown>;
  simulator_params: Record<string, unknown>;
  use_common_random_numbers: boolean;
}

export interface GuardrailVerdictRow {
  name: string;
  evaluated: boolean;
  fired: boolean;
  note: string;
}

export interface GateCallRow {
  attempt_number: number;
  at: string; // ISO 8601, the harness's simulated clock
  proposal_action_type: string;
  proposal_amount_paise: number | null;
  decision: "approved" | "rejected";
  reason: string;
  route_to: "NEEDS_REVIEW" | "NOT_WORKED" | null;
  idempotency_key: string;
  guardrail_table: GuardrailVerdictRow[];
}

export interface CaseAuditRow {
  case_id: string;
  case_kind: "corpus" | "crafted";
  crafted_note: string | null;
  decline_class: string;
  decline_class_source: "harvested" | "documented";
  error_code: string | null;
  error_reason: string | null;
  error_description: string | null;
  amount_paise: number;
  gate_calls: GateCallRow[];
  final_status: string;
  route_to: "NEEDS_REVIEW" | "NOT_WORKED" | null;
  outcome: "recovered" | "deferred_to_human_review" | "not_recovered";
}

export interface UnreachableGuardrailNote {
  name: string;
  why: string;
}

export interface CaseAuditArtifact {
  default_case_id: string;
  cases: CaseAuditRow[];
  structurally_unreachable_guardrails: UnreachableGuardrailNote[];
}

export interface ArtifactEnvelope<T> {
  schema_name: string;
  schema_version: string;
  manifest: ArtifactManifest;
  data: T;
}

// ============================================================================
// Stage 3 — day3_ablation
// ============================================================================

export interface ArmOutcomeRow {
  arm: string;
  recovered_rate: number;
  deferred_rate: number;
  not_recovered_rate: number;
  total_attempts: number;
  total_violations: number;
  recovered_amount_paise: number;
  deferred_amount_paise: number;
  net_value_paise: number;
}

export interface PairedLiftRow {
  arm_a: string;
  arm_b: string;
  n_cases: number;
  rate_a: number;
  rate_b: number;
  rate_lift: number;
  rate_lift_ci_low: number;
  rate_lift_ci_high: number;
  amount_lift_paise: number;
  amount_lift_ci_low_paise: number;
  amount_lift_ci_high_paise: number;
}

export interface GuardrailReachabilityRow {
  name: string;
  count: number;
  share: number;
  reachable: boolean | null;
  why: string;
}

export interface ComplianceEconomics {
  net_value_blind_retry_paise: number;
  net_value_rules_only_paise: number;
  violations_blind_retry: number;
  break_even_penalty_paise: number;
  break_even_penalty_usd: number;
  usd_to_inr: number;
  visa_penalty_paise: number;
  mastercard_low_paise: number;
  mastercard_high_paise: number;
}

export interface Day3AblationArtifact {
  n: number;
  master_seed: number;
  arms: ArmOutcomeRow[];
  lifts: PairedLiftRow[];
  guardrail_reachability: GuardrailReachabilityRow[];
  compliance: ComplianceEconomics;
}

// ============================================================================
// Stage 3 — day3_sweep. THE ONE RULE: `points` is the complete set of real,
// computed values for a parameter. Never interpolate between them.
// ============================================================================

export interface OATPoint {
  value: number;
  rate_control: number;
  rate_rules_only: number;
  rate_blind_retry: number;
  rate_lift_rules_vs_control: number;
  rules_beats_control: boolean;
  rate_lift_blind_vs_rules: number;
  blind_beats_rules: boolean;
  break_even_penalty_paise: number | null;
}

export interface OATParameterSweep {
  name: string;
  lo: number;
  hi: number;
  default: number;
  points: OATPoint[]; // exactly 5 — lo, 25%, default, 75%, hi
  lift_spread: number;
}

export interface JointSweepSummary {
  n_draws: number;
  n_cases_per_draw: number;
  rules_beats_control_count: number;
  n_draws_with_break_even: number;
  break_even_p5_paise: number;
  break_even_p50_paise: number;
  break_even_p95_paise: number;
  fraction_below_visa: number;
  fraction_below_mastercard_low: number;
  fraction_below_mastercard_high: number;
  visa_penalty_paise: number;
  mastercard_low_paise: number;
  mastercard_high_paise: number;
}

export interface Day3SweepArtifact {
  oat_n: number;
  base_seed: number;
  parameters: OATParameterSweep[];
  most_consequential: string[]; // sorted by lift_spread descending — the top two are the disclosed near-tie
  joint: JointSweepSummary;
}

// ============================================================================
// Stage 3 — day4_held_out_ablation
// ============================================================================

export interface LiftDistribution {
  mean: number;
  stdev: number;
  min: number;
  max: number;
  positive_seeds: number;
  total_seeds: number;
}

export interface ArmHeldOutRow {
  arm: string;
  is_shippable: boolean;
  mean_recovery_rate: number;
  total_violations: number;
  lift_vs_rules_only: LiftDistribution | null;
  total_yields: number | null;
}

export interface Day4HeldOutAblationArtifact {
  held_out_seeds: number[];
  n_per_seed: number;
  arms: ArmHeldOutRow[];
  modal_ranking: string[];
  modal_ranking_hold_count: number;
  per_seed_rankings: string[][];
}

// ============================================================================
// Stage 3 — day4_bound_decomposition
// ============================================================================

export interface RateBySeedRow {
  seed: number;
  rules_only: number;
  observable_optimal: number;
  oracle_upper_bound: number;
  oracle_value_maximizing: number;
}

export interface NetValueBySeedRow {
  seed: number;
  rules_only_paise: number;
  observable_optimal_paise: number;
  oracle_upper_bound_paise: number;
  oracle_value_maximizing_paise: number;
}

export interface GapStat {
  label: string;
  in_sample: number;
  held_out_mean: number;
  held_out_stdev: number;
  held_out_min: number;
  held_out_max: number;
  positive_at: number;
  total_points: number;
}

export interface Day4BoundDecompositionArtifact {
  proposal_seed: number;
  held_out_seeds: number[];
  rate_by_seed: RateBySeedRow[];
  net_value_by_seed_paise: NetValueBySeedRow[];
  rate_gap1: GapStat;
  rate_gap2: GapStat;
  net_value_gap1_paise: GapStat;
  net_value_gap2_paise: GapStat;
  dominance_check_holds_at_every_seed: boolean;
  dominance_check_failed_seeds: number[];
  attempts_conserved_net: number;
  attempts_reduced_by_class: Record<string, number>;
  attempts_increased_by_class: Record<string, number>;
  overfitting_gap_paise: number;
}

// ============================================================================
// Stage 3 — day4_bakeoff
// ============================================================================

export interface AbstentionCheckRow {
  rule: string;
  description: string;
  computed_value: string;
  threshold: string;
  fired: boolean;
}

export interface ProviderBakeoffResult {
  provider: string;
  model_id: string;
  n_calls: number;
  schema_valid_count: number;
  sensible_count: number;
  abstained: boolean;
  abstain_reason: string | null;
  checks: AbstentionCheckRow[];
  total_input_tokens: number;
  total_output_tokens: number;
}

export interface Day4BakeoffArtifact {
  proposal_seed: number;
  n_calls_per_provider: number;
  abstention_rule_commit_sha: string;
  abstention_rule_commit_date: string;
  bakeoff_commit_sha: string;
  bakeoff_commit_date: string;
  providers: ProviderBakeoffResult[];
}
