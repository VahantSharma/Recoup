"""The event-driven ablation harness: corpus + policies + simulator -> per-case,
per-arm outcome records — the raw material both the statistics and the sweep consume.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..corpus_builder import CaseDraft
from ..gate import ActionProposal
from ..gate import evaluate as gate_evaluate
from ..simulator.outcomes import CaseGroundTruth, attempt_succeeds, draw_ground_truth
from .clock import EventQueue
from .policies import AttemptHistoryEntry, ObservableCase, Policy

# Arms whose gate calls are audit_only — act regardless of the verdict, log a
# violation whenever it would have rejected. Everything else is enforced normally.
# Day 4's rules_plus_model arm is enforced too, by default, just by not being added here.
AUDIT_ONLY_ARMS = frozenset({"blind_retry"})


@dataclass(frozen=True)
class CaseArmResult:
    case_id: str
    arm: str
    amount_paise: int
    decline_class: str
    recovered: bool
    recovered_via: str | None  # "organic" | "action" | None
    resolved_at: datetime | None
    attempt_count: int  # action attempts actually executed
    violation_count: int  # gate rejections this arm acted through anyway (audit_only)
    final_status: str  # "recovered" | "not_recovered" | "gave_up_gate_rejected" | "gave_up_lifetime_exceeded"
    route_to: str | None  # None | "NEEDS_REVIEW" | "NOT_WORKED" -- copied verbatim
                           # from the gate's GateResult.route_to at the decision that
                           # ended this case's action-based path, if any
    outcome: str  # "recovered" | "deferred_to_human_review" | "not_recovered" -- the
                   # three-way split correction/instruction 3: NEEDS_REVIEW cases are
                   # a real, distinct outcome, not silently counted as "not recovered"


@dataclass
class _CaseState:
    case: ObservableCase
    ground_truth: CaseGroundTruth
    history: list[AttemptHistoryEntry] = field(default_factory=list)
    recovered: bool = False
    recovered_via: str | None = None
    resolved_at: datetime | None = None
    violation_count: int = 0
    # True once the ACTION path is exhausted (gate rejected, or lifetime exceeded)
    # -- deliberately does NOT mean "fully resolved." A case whose action path gave up
    # can still organically resolve later if its (independently scheduled) ORGANIC
    # event falls after the give-up point. Conflating the two was a real bug: an
    # earlier version used one `resolved` flag for both, which made the event loop's
    # `if state.resolved: continue` guard silently discard a still-pending, still-
    # legitimate ORGANIC event for any case whose action path had given up --
    # penalizing rules_only (which actually gives up on cases) for organic recoveries
    # control (which never gives up, because it never acts) still correctly counted.
    # Found via an OAT sweep result that shouldn't have been possible (rules_only's
    # lift over control going negative at high organic_recovery_rate_bps, when
    # rules_only's recovered set should be a strict superset of control's), not
    # assumed correct because the code looked reasonable.
    action_path_exhausted: bool = False
    final_status: str = "not_recovered"
    route_to: str | None = None
    pending_gate_decision: str | None = None
    pending_gate_reason: str | None = None

    def resolve(self, via: str, when: datetime) -> None:
        if self.recovered:
            return  # whichever event happens first wins; a later event for an
                     # already-recovered case is a no-op, not an error
        self.recovered = True
        self.recovered_via = via
        self.resolved_at = when
        self.final_status = "recovered"

    def give_up(self, reason: str, when: datetime, route_to: str | None = None) -> None:
        if self.recovered or self.action_path_exhausted:
            return
        self.action_path_exhausted = True
        self.resolved_at = when  # tentative -- overwritten if this case still
                                   # organically resolves after this point
        self.final_status = reason
        self.route_to = route_to

    @property
    def outcome(self) -> str:
        if self.recovered:
            return "recovered"
        if self.route_to == "NEEDS_REVIEW":
            return "deferred_to_human_review"
        return "not_recovered"


def _to_observable(draft: CaseDraft) -> ObservableCase:
    return ObservableCase(
        id=draft.razorpay_payment_id,
        amount=draft.amount,
        currency=draft.currency,
        decline_class=draft.decline_class,
        decline_class_source=draft.decline_class_source,
        risk_flagged=draft.risk_flagged,
        card_id=draft.card_id,
        simulated_at=draft.simulated_at,
    )


def _count_in_window(times: list[datetime], now: datetime, window_days: int) -> int:
    cutoff = now - timedelta(days=window_days)
    return sum(1 for t in times if cutoff <= t < now)


def _run_arm_impl(
    corpus: list[CaseDraft],
    policy: Policy,
    master_seed: int,
    retry_delay_hours: int,
    max_case_lifetime_days: int,
    guardrail_counts: dict[str, int] | None,
    use_common_random_numbers: bool = True,
) -> list[CaseArmResult]:
    """Runs one policy over the full corpus. Ground truth is drawn fresh here from the
    same (master_seed, case_id) every time this is called for the same case — that's
    what makes it identical across arms without needing to pass it in explicitly (the
    paired design's whole point).

    use_common_random_numbers: forwarded to every attempt_succeeds() call below. True
    (default) is the fixed, correct paired design -- see that function's docstring and
    docs/results.md's "Common random numbers" section for the bug this fixed. False
    reproduces the original, unpaired-in-effect behavior and exists only for
    tests/test_null_arm_lift_is_zero.py to measure the old noise floor directly.

    guardrail_counts, if given, is mutated in place: every gate.evaluate() call's
    GateResult.reason (one of the 8 guardrail names, or "permitted") is tallied there.
    Optional and separate from CaseArmResult on purpose -- run_arm/run_ablation's
    existing return shape is unchanged for every caller that doesn't need this."""
    queue = EventQueue()
    states: dict[str, _CaseState] = {}
    card_attempt_times: dict[str, list[datetime]] = {}
    audit_only = policy.name in AUDIT_ONLY_ARMS

    for draft in corpus:
        observable = _to_observable(draft)
        ground_truth = draw_ground_truth(
            case_id=observable.id,
            decline_class=observable.decline_class,
            master_seed=master_seed,
            case_simulated_at=observable.simulated_at,
            max_case_lifetime_days=max_case_lifetime_days,
        )
        states[observable.id] = _CaseState(case=observable, ground_truth=ground_truth)
        queue.schedule(observable.simulated_at, "ARRIVAL", observable.id)
        if ground_truth.organic_resolves_at is not None:
            queue.schedule(ground_truth.organic_resolves_at, "ORGANIC", observable.id)

    while len(queue):
        event = queue.pop()
        state = states[event.payload]
        if state.recovered:
            continue  # only a recovery is truly terminal for the event loop -- a case
                       # whose action path gave up (action_path_exhausted) can still
                       # have a legitimate pending ORGANIC event fire after this point

        if event.kind == "ORGANIC":
            state.resolve("organic", event.when)
            continue

        now = event.when

        if event.kind == "ACTION_DUE":
            attempt_number = len(state.history) + 1
            succeeded = attempt_succeeds(
                case_id=state.case.id, arm=policy.name, attempt_number=attempt_number,
                decline_class=state.case.decline_class, master_seed=master_seed,
                ground_truth=state.ground_truth,
                use_common_random_numbers=use_common_random_numbers,
            )
            state.history.append(AttemptHistoryEntry(
                attempt_number=attempt_number, action_type="retry_payment_link",
                gate_decision=state.pending_gate_decision or "approved",
                gate_reason=state.pending_gate_reason or "permitted",
                executed_at=now, outcome="recovered" if succeeded else "still_failed",
            ))
            if succeeded:
                state.resolve("action", now)
                continue
            # else falls through to propose the next attempt below

        # Simulation-level bound, not a business rule — see docs/assumptions.md's
        # max_case_lifetime_days. A real policy has no concept of this; the harness
        # enforces it before even asking, which is also what guarantees the event loop
        # terminates for every case (see test_harness_censoring.py).
        if now - state.case.simulated_at >= timedelta(days=max_case_lifetime_days):
            state.give_up("gave_up_lifetime_exceeded", now)
            continue

        card_id = state.case.card_id or state.case.id  # every real corpus case has a
                                                          # card; fallback only for
                                                          # hand-built test cases
        window_count = _count_in_window(card_attempt_times.setdefault(card_id, []), now, 30)

        # window_count is computed above propose() (not just before the gate call, as
        # it used to be) so a Policy can see its own card's contention and choose to
        # yield -- see ModelPlaybookPolicy. Reordering only, no new harness state: both
        # lines depend only on (now, card_id), never on the policy's output.
        proposal = policy.propose(state.case, state.history, now, window_count)
        if proposal.action_type == "yield_scarce_budget":
            # TERMINAL, same as every other give_up() path: this case's action path
            # never gets another attempt. Not "try again later" -- a policy voluntarily
            # forfeiting this case's entire remaining recovery probability, betting a
            # higher-weight case reaches the same card's freed slot first. route_to
            # stays None (a policy choice, not an escalation to human review), so this
            # correctly reads as "not_recovered" in the three-way outcome split while
            # final_status carries the distinct, auditable reason. See
            # docs/assumptions.md's scarcity_remaining_budget_threshold /
            # defer_priority_cutoff entries and docs/results.md's pre-registered note
            # on what it means if the grid search selects never-yield.
            state.give_up("gave_up_yielded_scarce_budget", now)
            continue
        if proposal.action_type != "retry_payment_link":
            continue  # nothing more scheduled on this path; a pending ORGANIC event, if any, stays queued

        result = gate_evaluate(
            case=state.case,  # duck-typed: gate.evaluate reads .decline_class,
                               # .risk_flagged, .amount -- ObservableCase has all three,
                               # by design (see policies.py's field-naming note)
            proposal=ActionProposal(action_type="retry_payment_link", amount_paise=proposal.amount_paise),
            reconciled_payment={"status": "failed"},  # simulated: the harness always
                                                        # knows the true current state
            reconciled_at=now,
            attempt_count_in_window=window_count,
            now=now,
            audit_only=audit_only,
        )
        if guardrail_counts is not None:
            guardrail_counts[result.reason] = guardrail_counts.get(result.reason, 0) + 1
        will_execute = (result.decision == "approved") or audit_only
        if result.decision == "rejected" and audit_only:
            state.violation_count += 1
        if not will_execute:
            state.give_up("gave_up_gate_rejected", now, route_to=result.route_to)
            continue

        execute_at = now + timedelta(hours=retry_delay_hours)
        card_attempt_times[card_id].append(execute_at)
        state.pending_gate_decision = result.decision
        state.pending_gate_reason = result.reason
        queue.schedule(execute_at, "ACTION_DUE", state.case.id)

    return [
        CaseArmResult(
            case_id=s.case.id, arm=policy.name, amount_paise=s.case.amount,
            decline_class=s.case.decline_class, recovered=s.recovered,
            recovered_via=s.recovered_via, resolved_at=s.resolved_at,
            attempt_count=len(s.history), violation_count=s.violation_count,
            final_status=s.final_status, route_to=s.route_to, outcome=s.outcome,
        )
        for s in states.values()
    ]


def run_arm(
    corpus: list[CaseDraft],
    policy: Policy,
    master_seed: int,
    retry_delay_hours: int,
    max_case_lifetime_days: int,
    use_common_random_numbers: bool = True,
) -> list[CaseArmResult]:
    return _run_arm_impl(
        corpus, policy, master_seed, retry_delay_hours, max_case_lifetime_days,
        guardrail_counts=None, use_common_random_numbers=use_common_random_numbers,
    )


def run_arm_with_guardrail_counts(
    corpus: list[CaseDraft],
    policy: Policy,
    master_seed: int,
    retry_delay_hours: int,
    max_case_lifetime_days: int,
    use_common_random_numbers: bool = True,
) -> tuple[list[CaseArmResult], dict[str, int]]:
    """Same as run_arm, plus a count of how many times each of the gate's 8 guardrail
    reasons (and "permitted") fired across every gate.evaluate() call this arm made --
    the evidence that the gate is actually being exercised, not decorative. Only
    meaningful for enforced arms that call the gate at all (control never does;
    blind_retry calls it audit_only and ignores the verdict, so its counts describe
    what *would* have been enforced, not what was)."""
    counts: dict[str, int] = {}
    results = _run_arm_impl(
        corpus, policy, master_seed, retry_delay_hours, max_case_lifetime_days,
        guardrail_counts=counts, use_common_random_numbers=use_common_random_numbers,
    )
    return results, counts


def run_ablation(
    corpus: list[CaseDraft],
    policies: list[Policy],
    master_seed: int,
    retry_delay_hours: int = 24,
    max_case_lifetime_days: int = 45,
    use_common_random_numbers: bool = True,
) -> dict[str, list[CaseArmResult]]:
    """Every arm runs over the *same* corpus with the *same* master_seed — the paired
    design. Each case's ground truth (drawn inside run_arm from (master_seed,
    case_id), independent of arm) is therefore identical across arms; and, as of the
    common-random-numbers fix (see app.simulator.outcomes.attempt_succeeds), so is
    every per-attempt success draw a case shares across arms that actually reach it --
    only what each policy DOES (whether it attempts, how many times, when) differs."""
    return {
        policy.name: run_arm(
            corpus, policy, master_seed, retry_delay_hours, max_case_lifetime_days,
            use_common_random_numbers=use_common_random_numbers,
        )
        for policy in policies
    }
