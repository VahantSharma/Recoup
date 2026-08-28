import { decisiveReason } from "./outcome";
import type { CaseAuditRow } from "./artifacts/types";

/**
 * A reviewer who has never seen this system before shouldn't have to decode
 * "hard_decline_stop" or "amount_ceiling_needs_signoff" to understand what happened.
 * One plain sentence per guardrail, built entirely from the same real field
 * (decisive gate reason) already shown technically elsewhere on the screen -- no new
 * claim, just the existing enum value said in words. The exact guardrail name stays
 * visible right beside it (mono, small) for anyone who wants the technical trace.
 */
const GUARDRAIL_PLAIN_LANGUAGE: Record<string, string> = {
  permitted: "Nothing blocked it — retried automatically.",
  stale_reconcile: "The last status check was too old to trust, so the system refused to act on it.",
  unclassifiable_decline_human_review: "Razorpay returned a reason nobody has classified yet — sent to a person instead of guessed at.",
  hard_decline_stop: "A permanent decline — blocked card, closed account. Never retried, by design.",
  risk_hard_stop: "Flagged as fraud risk — never auto-retried. A person reviews it instead.",
  already_resolved: "The payment had already resolved elsewhere by the time the system checked.",
  amount_ceiling_needs_signoff: "Above the auto-approve limit — a person signs off before any retry.",
  network_attempt_budget_exhausted: "This card already hit its retry cap for the window — the card network sets that limit, not us.",
  break_even_floor: "The math says a retry would cost more than it's likely to recover — so the system doesn't bother.",
};

/** The plain-language gloss for one guardrail name (or "permitted") on its own --
 * used inline in the guardrail table, right where the technical verdict is shown. */
export function guardrailPlainLanguage(reason: string): string {
  return GUARDRAIL_PLAIN_LANGUAGE[reason] ?? reason;
}

/**
 * One sentence: what happened to this case, in plain language, and how it ended if
 * that ending wasn't the obvious consequence of the guardrail that fired (e.g. a
 * budget-exhausted case that still resolved organically afterward).
 */
export function plainLanguageSummary(row: CaseAuditRow): string {
  const reason = decisiveReason(row);
  const base = reason ? guardrailPlainLanguage(reason) : "No action was ever proposed for this case.";
  if (row.outcome === "recovered" && reason !== "permitted") {
    return `${base} It recovered on its own anyway.`;
  }
  return base;
}
