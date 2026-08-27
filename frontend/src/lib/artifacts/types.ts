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
