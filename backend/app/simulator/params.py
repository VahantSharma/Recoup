"""What actually HAPPENS — ground truth for Day 3's outcome simulator.

NOTHING outside backend/app/simulator/ may import this module — enforced by
backend/tests/test_import_boundary.py, not just convention. This is Recoup's answer to
the circularity risk: the policy's belief about recovery odds
(app.policy_params.POLICY_PRIOR_RECOVERY_RATE_BPS) and the simulator's ground truth
below start from the same unsourced default today but are swept independently and made
to diverge on Day 3, so the ablation can test whether a compliant policy still wins
when its belief is wrong — rather than the policy silently reading the answer key.
"""
from __future__ import annotations

# HEADLINE RISK (docs/assumptions.md) — NO PUBLIC SOURCE FOUND. Same starting default
# as app.policy_params.POLICY_PRIOR_RECOVERY_RATE_BPS today; Day 3 sweeps this
# independently, including runs that diverge from the policy prior by up to ±2000 bps.
SIM_TRUE_RECOVERY_RATE_BPS: dict[str, int] = {
    "hard": 0,
    "soft": 5500,
    "technical": 5500,
}
