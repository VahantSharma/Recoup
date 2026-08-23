"""What actually HAPPENS — ground truth for Day 3's outcome simulator.

NOTHING outside backend/app/simulator/ may import this module — enforced by
backend/tests/test_import_boundary.py, not just convention. This is Recoup's answer to
the circularity risk: the policy's belief about recovery odds
(app.policy_params.POLICY_PRIOR_RECOVERY_RATE_BPS) and the simulator's ground truth
below start from the same unsourced default today but are swept independently and made
to diverge on Day 3, so the ablation can test whether a compliant policy still wins
when its belief is wrong — rather than the policy silently reading the answer key.

Two-level recoverability (Day 3), not a flat per-attempt rate: a case's fate is
decided by two independent facts, both NO PUBLIC SOURCE FOUND, see
docs/assumptions.md's HEADLINE RISK section —
  1. P_CASE_RECOVERABLE_BPS — drawn ONCE per case. Some cases are genuinely dead
     (closed account, no funds ever coming); no action and no amount of time recovers
     them, ever, by any arm. This is the fix for the flat-rate model's real flaw:
     enough independent per-attempt draws at a fixed rate drives cumulative recovery
     probability toward 1 regardless of whether the case was ever alive.
  2. SIM_TRUE_RECOVERY_RATE_BPS — per-attempt success probability CONDITIONAL on the
     case already being recoverable. Redefined from Day 2's flat-rate meaning; same
     starting numbers, different semantics.
Plus ORGANIC_RECOVERY_RATE_BPS: whether a recoverable case self-resolves with no
action taken at all — the control arm's actual baseline. Without this the control arm
recovers nothing by construction and every other arm's "lift" collapses into gross
recovery, the exact circularity a control arm exists to prevent.
"""
from __future__ import annotations

# HEADLINE RISK (docs/assumptions.md) — the single most consequential parameter in the
# whole project: it sets the baseline every arm's lift is measured against. Range
# deliberately wider than every other HEADLINE RISK parameter (see the register) —
# least evidence, most riding on it.
ORGANIC_RECOVERY_RATE_BPS: dict[str, int] = {
    "hard": 0,
    "soft": 2500,
    "technical": 2500,
}

# HEADLINE RISK — drawn once per case (app.simulator.outcomes.draw_ground_truth), not
# per attempt. 'technical' > 'soft' here while SIM_TRUE_RECOVERY_RATE_BPS below is
# equal across both — 'technical' dominates 'soft' on every axis at these defaults.
# Checked explicitly in the Day 3 OAT sweep against hard_share_of_nonsoft, which
# controls how much of the corpus is 'technical' at all.
P_CASE_RECOVERABLE_BPS: dict[str, int] = {
    "hard": 0,
    "soft": 8000,
    "technical": 9000,
}

# HEADLINE RISK. Same starting default as app.policy_params.POLICY_PRIOR_RECOVERY_RATE_BPS
# today; Day 3 sweeps this independently, including runs that diverge from the policy
# prior by up to ±2000 bps. Redefined (Day 3): conditional on P_CASE_RECOVERABLE_BPS's
# roll having already succeeded for this case — not evaluated at all otherwise.
SIM_TRUE_RECOVERY_RATE_BPS: dict[str, int] = {
    "hard": 0,
    "soft": 5500,
    "technical": 5500,
}
