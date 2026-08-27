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
from .observable_optimal import ObservableOptimalParams, should_yield_by_value


class OracleUpperBoundPolicy:
    """Objective, stated explicitly (Task A2, Problem 1 correction): this class does
    NOT maximize net value, and does not deliberately maximize recovery count either.
    Among cases it knows are recoverable, it applies NO value-weighting at all --
    every recoverable case is attempted, first-come, identically to how RulesOnlyPolicy
    orders attempts. Its only decision is a hard filter: skip a case iff ground truth
    says it can never recover, for any number of attempts. Because that filter frees
    shared card capacity that would otherwise be wasted, and does so without regard to
    which competing case benefits, its emergent behavior looks CLOSER to
    count-maximizing than value-maximizing -- worth stating precisely rather than
    assuming, since it is exactly what makes rate_lift the right metric for THIS
    class's own gap and net-value lift the wrong one. See OracleValueMaximizingPolicy
    below for the objective-matched variant against ObservableOptimalPolicy, and
    docs/results.md's Task A2 section for why both are reported, each against its own
    matching metric.
    """

    name = "oracle_upper_bound"

    def __init__(self, master_seed: int, max_case_lifetime_days: int):
        # Must match the master_seed/max_case_lifetime_days the caller passes to
        # run_arm/run_ablation for this same run -- passed explicitly rather than
        # threaded implicitly, so the coupling is visible at every call site instead
        # of hidden inside this class.
        self._master_seed = master_seed
        self._max_case_lifetime_days = max_case_lifetime_days

    def _is_recoverable(self, case) -> bool:
        return draw_ground_truth(
            case_id=case.id,
            decline_class=case.decline_class,
            master_seed=self._master_seed,
            case_simulated_at=case.simulated_at,
            max_case_lifetime_days=self._max_case_lifetime_days,
        ).is_recoverable

    def propose(self, case, history, now, card_attempts_in_window) -> ActionProposal:
        if not self._is_recoverable(case):
            # The one decision no real Policy can make: this case can never recover,
            # by any number of attempts, so don't spend a shared card's scarce budget
            # finding that out the hard way. Applies to EVERY decline class ground
            # truth marks unrecoverable, not just 'hard' -- a 'soft' or 'technical'
            # case ground truth says will never recover gets skipped exactly the same
            # way, and that IS where this class's real advantage over rules_only lives
            # (a hard-decline case never reaches the gate for rules_only either, so
            # skipping it costs nothing either way -- see docs/results.md's corrected
            # Task A claim-2 writeup).
            return ActionProposal(action_type="no_action")
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)


class OracleValueMaximizingPolicy:
    """The objective-matched ceiling for ObservableOptimalPolicy (Task A2, Problem 1
    correction): identical perfect-recoverability filter as OracleUpperBoundPolicy,
    PLUS the identical value-weighted yield mechanism ObservableOptimalPolicy uses
    (should_yield_by_value, imported not reimplemented) among cases known to be
    recoverable. Holding the allocation MECHANISM constant and varying only the
    INFORMATION (ground truth vs. observable features) is what makes
    oracle_value_maximizing - observable_optimal a clean measurement of the value of
    information alone -- an independently-fit oracle-specific value search would
    confound 'better information' with 'different fitted parameters'.

    Reuses ObservableOptimalPolicy's ALREADY-FIT params (from
    run_observable_optimal_search) rather than fitting its own -- deliberately: the
    question this class answers is 'how much does ALSO knowing ground truth add,
    given the same value-allocation rule', not 'what is the best possible
    value-allocation rule under perfect information' (a different, harder question,
    out of scope here)."""

    name = "oracle_value_maximizing"

    def __init__(self, oo_params: ObservableOptimalParams, master_seed: int, max_case_lifetime_days: int):
        self._oo_params = oo_params
        self._master_seed = master_seed
        self._max_case_lifetime_days = max_case_lifetime_days

    def _is_recoverable(self, case) -> bool:
        return draw_ground_truth(
            case_id=case.id,
            decline_class=case.decline_class,
            master_seed=self._master_seed,
            case_simulated_at=case.simulated_at,
            max_case_lifetime_days=self._max_case_lifetime_days,
        ).is_recoverable

    def propose(self, case, history, now, card_attempts_in_window) -> ActionProposal:
        if not self._is_recoverable(case):
            return ActionProposal(action_type="no_action")
        attempt_number = len(history) + 1
        time_since_failure_days = (now - case.simulated_at).total_seconds() / 86_400
        if should_yield_by_value(
            self._oo_params, decline_class=case.decline_class, amount_paise=case.amount,
            attempt_number=attempt_number, time_since_failure_days=time_since_failure_days,
            card_attempts_in_window=card_attempts_in_window,
        ):
            return ActionProposal(action_type="yield_scarce_budget")
        return ActionProposal(action_type="retry_payment_link", amount_paise=case.amount)
