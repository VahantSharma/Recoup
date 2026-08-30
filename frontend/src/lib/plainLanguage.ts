import { decisiveReason } from "./outcome";
import type { CaseAuditRow } from "./artifacts/types";

/**
 * The one place every raw backend identifier (a guardrail's snake_case reason, a
 * decline reason string, "hard"/"soft"/"technical", "documented"/"harvested", a
 * final_status value, an arm name) gets turned into plain English. A reviewer who has
 * never seen this system before should never have to decode "hard_decline_stop" or
 * "amount_ceiling_needs_signoff" to understand what happened -- and nothing new can
 * reach a screen untranslated, because every screen that shows one of these values
 * calls a function from here, never renders the raw string directly.
 *
 * The raw identifier is never hidden, only demoted: it stays visible as small,
 * secondary (usually mono) text next to the plain label, for anyone who wants the
 * exact technical name -- see e.g. GuardrailTable.tsx's own layout. Translating, not
 * hiding.
 */

// --- guardrails: a short label for the primary slot, plus "what this protects
// against" for the one-line explanation every guardrail carries -- see gate.py's
// GUARDRAIL_ORDER for the real, checked order these names come from. ---

export interface GuardrailCopy {
  label: string; // short, plain -- the PRIMARY thing a reviewer reads
  protects: string; // "what this protects against," one line
}

const GUARDRAIL_COPY: Record<string, GuardrailCopy> = {
  permitted: {
    label: "Nothing blocked it",
    protects: "Nothing to guard against here — every check passed, so the retry went ahead.",
  },
  stale_reconcile: {
    label: "Payment status too old to act on",
    protects: "Stops us from acting on information about the payment that might already be out of date.",
  },
  unclassifiable_decline_human_review: {
    label: "Unrecognized reason — sent to a person",
    protects: "Stops us from guessing at a decline reason we've never seen and don't understand yet.",
  },
  hard_decline_stop: {
    label: "Permanent decline — never retried",
    protects: "Stops us from repeatedly trying a card that will never work again (stolen, closed, blocked).",
  },
  risk_hard_stop: {
    label: "Flagged as risky — sent to a person",
    protects: "Stops us from retrying a payment that looks like fraud.",
  },
  already_resolved: {
    label: "Already paid elsewhere",
    protects: "Stops us from charging a customer twice for money we've already collected another way.",
  },
  amount_ceiling_needs_signoff: {
    label: "Amount too large — needs sign-off",
    protects: "Stops a large amount from being retried automatically with nobody checking it first.",
  },
  network_attempt_budget_exhausted: {
    label: "Retry limit reached",
    protects: "Stops us from retrying a card so often that the card network fines us for it.",
  },
  break_even_floor: {
    label: "Not worth acting on",
    protects: "Stops us from spending more trying to collect a payment than the payment is actually worth.",
  },
};

/** Short label for a guardrail's primary slot -- falls back to the raw name only if
 * something genuinely untranslated reaches here, which is itself a bug worth seeing. */
export function guardrailShortLabel(reason: string): string {
  return GUARDRAIL_COPY[reason]?.label ?? reason;
}

/** "What this protects against," one line -- empty for "permitted", which protects
 * against nothing (it's the absence of a block, not a rule). */
export function guardrailProtects(reason: string): string {
  return GUARDRAIL_COPY[reason]?.protects ?? "";
}

// --- longer, situational one-liners -- what actually happened to THIS case, used in
// the case-list row summary. Kept separate from the short label above: a heading
// needs three words, a summary needs a full sentence, and conflating the two either
// makes headings too long or summaries too terse. ---

const GUARDRAIL_PLAIN_LANGUAGE: Record<string, string> = {
  permitted: "Nothing blocked it — retried automatically.",
  stale_reconcile: "The last status check was too old to trust, so the system refused to act on it.",
  unclassifiable_decline_human_review: "Razorpay returned a reason nobody has classified yet — sent to a person instead of guessed at.",
  hard_decline_stop: "A permanent decline — blocked card, closed account. Never retried, by design.",
  risk_hard_stop: "Flagged as fraud risk — never auto-retried. A person reviews it instead.",
  already_resolved: "The status check didn't come back as a confirmed still-failed payment — sent to a person to confirm, rather than assumed safe to retry.",
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

// --- decline reasons: Razorpay's own 17 published reason strings, plus the one
// harvested one (payment_failed) -- see backend/app/taxonomy.py's REASON_TAXONOMY,
// the single source of truth this list mirrors. ---

const DECLINE_REASON_LABEL: Record<string, string> = {
  payment_failed: "Payment failed",
  insufficient_funds: "Not enough money in the account",
  transaction_limit_exceeded: "Card's transaction limit hit",
  card_declined: "Card declined by the bank",
  debit_declined: "Debit declined by the bank",
  payment_declined: "Payment declined",
  debit_instrument_blocked: "Card is blocked",
  card_expired: "Card has expired",
  card_number_invalid: "Card number isn't valid",
  incorrect_cvv: "Wrong security code (CVV)",
  international_transaction_not_allowed: "International payments not allowed on this card",
  payment_risk_check_failed: "Flagged as risky by the bank",
  payment_timed_out: "The payment timed out",
  issuer_technical_error: "A technical error at the customer's bank",
  bank_technical_error: "A technical error at the bank",
  gateway_technical_error: "A technical error in the payment gateway",
  server_error: "A server error",
  authentication_failed: "Authentication failed (for example, a wrong OTP)",
};

export function declineReasonLabel(reason: string | null): string {
  if (!reason) return "No reason given";
  return DECLINE_REASON_LABEL[reason] ?? reason;
}

// --- the hard / soft / technical classification (Recoup's own work, not Razorpay's
// -- see CLAUDE.md) ---

const DECLINE_CLASS_LABEL: Record<string, string> = {
  hard: "Never retried",
  soft: "Worth retrying",
  technical: "Safe to retry fast",
};

export function declineClassLabel(declineClass: string): string {
  return DECLINE_CLASS_LABEL[declineClass] ?? declineClass;
}

// --- evidence source: how sure we are about a fact, not just what the fact is --
// mirrors the landing page's own evidence-tier wording so the same claim reads the
// same way everywhere on the site. ---

const EVIDENCE_SOURCE_LABEL: Record<string, string> = {
  documented: "Published by Razorpay, not observed live by us",
  harvested: "Observed live by us, on a real payment",
};

export function evidenceSourceLabel(source: string): string {
  return EVIDENCE_SOURCE_LABEL[source] ?? source;
}

// A short, badge-safe version of the same claim -- badges are a fixed-height, single-
// line "ink stamp" (see Badge.css's deliberate `white-space: nowrap`) built for short
// tags like "OK" or "WARN", not full sentences; forcing a full sentence into one badge
// overflows the page at narrow widths. The full sentence above still reaches the
// reviewer -- it's what the adjacent InfoTip says -- this is only the pill's own label.
const EVIDENCE_SOURCE_SHORT_LABEL: Record<string, string> = {
  documented: "Documented",
  harvested: "Verified live",
};

export function evidenceSourceShortLabel(source: string): string {
  return EVIDENCE_SOURCE_SHORT_LABEL[source] ?? source;
}

// --- final_status: how a case's action-taking path actually ended, distinct from
// its overall outcome badge (recovered / human review / not worked / refused) --
// see app/harness/run.py's CaseArmResult.final_status for the real value set. ---

const FINAL_STATUS_LABEL: Record<string, string> = {
  recovered: "Recovered",
  not_recovered: "Not recovered",
  gave_up_gate_rejected: "Stopped — a safety rule said no",
  gave_up_lifetime_exceeded: "Stopped — ran out of time to keep trying",
  gave_up_yielded_scarce_budget: "Stopped — gave its turn to another payment on the same card",
  excluded_opted_out: "Never attempted — the customer opted out of contact",
};

export function finalStatusLabel(status: string): string {
  return FINAL_STATUS_LABEL[status] ?? status;
}

// --- arm names: the eight things being compared across the ablation/decomposition
// screens -- see backend/scripts/run_day4_ablation.py's ALL_ARMS for the real list. ---

const ARM_LABEL: Record<string, string> = {
  control: "Did nothing (baseline)",
  blind_retry: "Retry everything, no rules",
  rules_only: "Our rules engine",
  tuned_weights: "Rules, auto-tuned",
  rules_plus_model_gemini: "Rules + Gemini AI",
  rules_plus_model_groq: "Rules + Groq AI",
  observable_optimal: "Best possible, using only real information",
  oracle_upper_bound: "Perfect-information ceiling",
  oracle_value_maximizing: "Perfect-information ceiling (value-matched)",
};

export function armLabel(arm: string): string {
  return ARM_LABEL[arm] ?? arm;
}
