import type { CaseAuditRow } from "./artifacts/types";

export type Tone = "ok" | "warn" | "stop";

export interface OutcomeDescription {
  label: string;
  tone: Tone;
}

/**
 * One case's outcome, reduced to exactly the four badge categories the sidebar shows:
 * recovered / human review / not worked / refused. Checked in this order because a
 * case can be routed to NEEDS_REVIEW or NOT_WORKED by its decisive gate call and still
 * resolve organically afterward (see app.harness.run's give_up/resolve split) -- the
 * FINAL outcome always wins over the routing that got it there.
 */
export function describeOutcome(row: CaseAuditRow): OutcomeDescription {
  if (row.outcome === "recovered") return { label: "recovered", tone: "ok" };
  if (row.route_to === "NEEDS_REVIEW") return { label: "human review", tone: "warn" };
  // NOT_WORKED and a route-less terminal refusal both read as --stop, matching the
  // guardrail table's own rule (only a NEEDS_REVIEW route earns --warn) -- the color
  // means the same thing in both places on this screen.
  if (row.route_to === "NOT_WORKED") return { label: "not worked", tone: "stop" };
  return { label: "refused", tone: "stop" };
}

/** Tone for the guardrail-table band: --warn only for a human-review route, --stop for
 * every other refusal (including a deliberate not-worked). */
export function toneForRouteTo(routeTo: string | null): Tone {
  return routeTo === "NEEDS_REVIEW" ? "warn" : "stop";
}

/** The guardrail (or "permitted") that decided a case -- its LAST gate call's reason. */
export function decisiveReason(row: CaseAuditRow): string | null {
  const calls = row.gate_calls;
  return calls.length > 0 ? calls[calls.length - 1].reason : null;
}
