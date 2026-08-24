"""The oracle-upper-bound arm: a deterministic measurement CEILING, not a submittable
policy, not a model, no network call. Explains the Day 4 null (tuned_weights ==
rules_only exactly, under CRN) by isolating exactly one question: is there ANY
headroom for an allocator -- LLM-synthesized, grid-searched, or otherwise -- to find
by reallocating the shared rolling-30-day card budget, if it had PERFECT knowledge of
which cases can ever recover?

OracleUpperBoundPolicy re-derives each case's ground-truth recoverability itself, by
calling app.simulator.outcomes.draw_ground_truth directly with the same inputs the
harness uses -- draw_ground_truth is a pure function of (master_seed, case_id,
decline_class, case_simulated_at, max_case_lifetime_days), so this is guaranteed to
match the harness's own draw, not a separate/divergent computation. It then makes
exactly one decision no real Policy can make: never spend a card's scarce attempt
budget on a case that is provably never going to recover. Every other case gets the
identical retry-until-give-up treatment RulesOnlyPolicy gives it, through the
identical gate, so oracle_upper_bound - rules_only isolates the value of PERFECT
recoverability information specifically -- not a better retry schedule, not a smarter
amount ceiling, just never wasting a shared slot on a hopeless case.

This is A ceiling, not THE global optimum: a more sophisticated oracle could also
sequence WHICH recoverable case gets a contended card's next slot (by ticket size, by
remaining lifetime, ...) for a possibly-higher ceiling still. This one isolates the
single cleanest, most directly comparable lever -- the same lever Day 4's
yield-at-scarcity mechanism (app.harness.policies.ModelPlaybookPolicy) tries to
approximate blindly, via a per-class weight/cutoff heuristic instead of perfect
per-case information. oracle_upper_bound - rules_only is therefore the honest ceiling
for whatever ANY allocator working through that same mechanism could ever have found;
it is not a claim that no larger ceiling exists via a different mechanism entirely.

Deliberately not exported from app.harness.policies, which stays checked by
tests/test_import_boundary.py (see that test's own regression guard). This module is
exempted the same way app.harness.run/sweep are, for the same reason: importing
app.simulator here is the entire point, not a leak -- see that test's docstring.
Conforms to the exact same Policy protocol shape used everywhere else, so it runs
through the unmodified app.harness.run.run_arm/run_ablation with zero special-casing.
"""
from __future__ import annotations

from ..gate import ActionProposal
from ..simulator.outcomes import draw_ground_truth


class OracleUpperBoundPolicy:
    name = "oracle_upper_bound"

    def __init__(self, master_seed: int, max_case_lifetime_days: int):
        # Must match the master_seed/max_case_lifetime_days the caller passes to
        # run_arm/run_ablation for this same run -- passed explicitly rather than
        # threaded implicitly, so the coupling is visible at every call site instead
        # of hidden inside this class.
        self._master_seed = master_seed
        self._max_case_lifetime_days = max_case_lifetime_days

    def propose(self, case, history, now, card_attempts_in_window) -> ActionProposal:
        ground_truth = draw_ground_truth(
            case_id=case.id,
            decline_class=case.decline_class,
            master_seed=self._master_seed,
            case_simulated_at=case.simulated_at,
            max_case_lifetime_days=self._max_case_lifetime_days,
        )
        if not ground_truth.is_recoverable:
            # The one decision no real Policy can make: this case can never recover,
            # by any number of attempts, so don't spend a shared card's scarce budget
            # finding that out the hard way.
            return ActionProposal(action_type="no_action")
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)
