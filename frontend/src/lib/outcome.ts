import type { CaseAuditRow } from "./artifacts/types";

// "policy" is a deliberately distinct fourth tone, not a synonym for "stop" -- a
// NOT_WORKED case (break_even_floor: the gate could act but the expected value says
// don't) is a different KIND of thing than a hard compliance/fraud stop, and CLAUDE.md
// says so explicitly: "declining to act is a feature, and it gets logged." Coloring it
// identically to a blocked-card refusal was a real doctrine violation, caught in
// review, not a taste call -- see docs/results.md's guardrail reachability table for
// why break_even_floor is reachable only via a crafted example in the first place.
export type Tone = "ok" | "warn" | "stop" | "policy";

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
  if (row.route_to === "NOT_WORKED") return { label: "not worked", tone: "policy" };
  return { label: "refused", tone: "stop" };
}

/** Tone for the guardrail-table band: --warn for a human-review route, --policy for a
 * deliberate not-worked (a choice, not a stop), --stop for every other refusal. */
export function toneForRouteTo(routeTo: string | null): Tone {
  if (routeTo === "NEEDS_REVIEW") return "warn";
  if (routeTo === "NOT_WORKED") return "policy";
  return "stop";
}

/** The guardrail (or "permitted") that decided a case -- its LAST gate call's reason. */
export function decisiveReason(row: CaseAuditRow): string | null {
  const calls = row.gate_calls;
  return calls.length > 0 ? calls[calls.length - 1].reason : null;
}
