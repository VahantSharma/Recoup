"""What the gate BELIEVES — every policy-side numeric knob, sourced or flagged in
docs/assumptions.md.

Never import anything from `app.simulator` here, or anywhere else under `app/` outside
`app/simulator/` itself — that's the ground truth the simulator uses to decide real
outcomes, and the policy reading it (even indirectly, via a shared config) would be
the exact circularity CLAUDE.md is built to avoid. Enforced structurally by
`tests/test_import_boundary.py`, not just this docstring.
"""
from __future__ import annotations

# --- HEADLINE RISK (docs/assumptions.md) — NO PUBLIC SOURCE FOUND for either ---
# Same starting default as app.simulator.params.SIM_TRUE_RECOVERY_RATE_BPS today;
# Day 3 sweeps the two independently, including runs that deliberately diverge by up
# to ±2000 bps, to test whether the compliant policy still wins when its belief about
# recovery odds is wrong.
POLICY_PRIOR_RECOVERY_RATE_BPS: dict[str, int] = {
    "hard": 0,  # never retried by policy — the value is moot
    "soft": 5500,
    "technical": 5500,
}

# --- policy priors, docs/assumptions.md "Policy priors" section ---
ATTEMPT_DECAY_FACTOR = 0.7  # NO PUBLIC SOURCE FOUND — see assumptions.md
COST_PER_CONTACT_ATTEMPT_MILLI_PAISE = 115  # ₹0.115 — verified, MyOperator (low end of a [115,145] range)
AMOUNT_CEILING_PAISE = 500_000  # ₹5,000 — policy knob, not empirical
NETWORK_ATTEMPT_BUDGET_PER_CARD_30D = 6  # deliberate headroom below the lowest verified cap (15)
RECONCILE_FRESHNESS_WINDOW_SECONDS = 300  # 5 minutes — engineering policy knob


def effective_recovery_rate_bps(decline_class: str, attempt_number: int) -> int:
    """Recovery-rate prior for the attempt about to be made, decayed from attempt 1's
    base rate by ATTEMPT_DECAY_FACTOR — not a flat first-attempt prior applied to
    every later attempt. Integer bps in, integer bps out; see docs/assumptions.md's
    unit conventions for why the break-even math stays float-free everywhere except
    this one rounding step (attempt_decay_factor is a sampling-shape float, not a
    money value)."""
    base = POLICY_PRIOR_RECOVERY_RATE_BPS.get(decline_class, 0)
    if attempt_number <= 1:
        return base
    return round(base * (ATTEMPT_DECAY_FACTOR ** (attempt_number - 1)))
