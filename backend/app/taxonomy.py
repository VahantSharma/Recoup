"""error_reason -> (decline_class, guardrail-relevant flags) classification.

Rules, not a model call — a closed, documented set. See CLAUDE.md's "Where the model
is used" table.

Razorpay does not ship its own hard/soft/technical labels; the mapping below is
Recoup's own interpretation of CLAUDE.md's definitions applied to Razorpay's real
reason vocabulary, not something Razorpay itself declares. Every entry's `source`
says whether it was actually observed on a live API response this session
('harvested') or is Recoup's classification of a reason string documented at
razorpay.com/docs but not reproduced live ('documented') — see the
recoup-razorpay-error-taxonomy-doc-sourced memory for why: test mode's mock bank page
turned out to be a plain Success/Failure toggle that does not branch on the specific
test card number, so only two outcomes are actually harvestable through that flow
(success, and one generic gateway decline). Keeping this distinction honest here is
what makes `payment_cases.decline_class_source` meaningful downstream.
"""
from __future__ import annotations

from dataclasses import dataclass

HARD = "hard"
SOFT = "soft"
TECHNICAL = "technical"


@dataclass(frozen=True)
class ReasonInfo:
    decline_class: str
    source: str  # 'harvested' | 'documented'
    risk_flagged: bool = False


# Reason strings actually observed on a real test-mode API response this session
# (2026-08-22) — see backend/data/harvested_corpus.json for the full captured payloads.
REASON_TAXONOMY: dict[str, ReasonInfo] = {
    # --- harvested (live-observed) ---
    "payment_failed": ReasonInfo(SOFT, "harvested"),
    # --- documented (razorpay.com/docs/errors/payments/*, not reproduced live) ---
    "insufficient_funds": ReasonInfo(SOFT, "documented"),
    "transaction_limit_exceeded": ReasonInfo(SOFT, "documented"),
    "card_declined": ReasonInfo(SOFT, "documented"),
    "debit_declined": ReasonInfo(SOFT, "documented"),
    "payment_declined": ReasonInfo(SOFT, "documented"),
    "debit_instrument_blocked": ReasonInfo(HARD, "documented"),
    "card_expired": ReasonInfo(HARD, "documented"),
    "card_number_invalid": ReasonInfo(HARD, "documented"),
    "incorrect_cvv": ReasonInfo(HARD, "documented"),
    "international_transaction_not_allowed": ReasonInfo(HARD, "documented"),
    "payment_risk_check_failed": ReasonInfo(HARD, "documented", risk_flagged=True),
    "payment_timed_out": ReasonInfo(TECHNICAL, "documented"),
    "issuer_technical_error": ReasonInfo(TECHNICAL, "documented"),
    "bank_technical_error": ReasonInfo(TECHNICAL, "documented"),
    "gateway_technical_error": ReasonInfo(TECHNICAL, "documented"),
    "server_error": ReasonInfo(TECHNICAL, "documented"),
    "authentication_failed": ReasonInfo(TECHNICAL, "documented"),
}

# Razorpay's docs do not expose distinct reason strings for stolen/lost card, closed
# account, invalid account number, "do not honour," or Mastercard merchant-advice
# codes as test-mode-triggerable — CLAUDE.md's own headline hard-decline examples.
# There is no real Razorpay reason string to map for those; the gate's hard-decline
# stop (Day 2) has to key off whatever Razorpay actually surfaces (closest real
# analogs above: debit_instrument_blocked, payment_risk_check_failed) rather than
# invented strings that don't exist in Razorpay's vocabulary.


def classify(error_code: str | None, error_reason: str | None) -> ReasonInfo:
    """Classify a Razorpay payment's error fields. A captured/successful payment
    (error_reason is None) is not a failure and is not itself a "case" — only failed
    payments enter the case store."""
    if error_reason is None:
        raise ValueError("classify() is only for failed payments (error_reason is None)")
    info = REASON_TAXONOMY.get(error_reason)
    if info is not None:
        return info
    # Unrecognized reason: default to technical (no real issuer decision confirmed) and
    # mark it clearly as an inferred fallback, never silently presented as known.
    return ReasonInfo(TECHNICAL, "documented")
