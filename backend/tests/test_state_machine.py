from datetime import datetime, timezone

import pytest

from app.state_machine import LEGAL_TRANSITIONS, TERMINAL_STATES, IllegalTransition, transition


class FakeCase:
    """A stand-in for PaymentCase — transition() only needs .state/.state_updated_at."""

    def __init__(self, state: str) -> None:
        self.state = state
        self.state_updated_at = None


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_legal_transition_succeeds():
    case = FakeCase("INTAKE")
    transition(case, "CLASSIFIED", now=_now)
    assert case.state == "CLASSIFIED"
    assert case.state_updated_at == _now()


def test_illegal_transition_raises_and_leaves_state_unchanged():
    case = FakeCase("INTAKE")
    with pytest.raises(IllegalTransition):
        transition(case, "ACTED", now=_now)
    assert case.state == "INTAKE"
    assert case.state_updated_at is None


def test_every_declared_target_state_is_itself_declared():
    for state, targets in LEGAL_TRANSITIONS.items():
        for t in targets:
            assert t in LEGAL_TRANSITIONS, f"{state} -> {t} but {t!r} is not a declared state"


def test_terminal_states_have_no_outgoing_transitions():
    for s in TERMINAL_STATES:
        assert LEGAL_TRANSITIONS[s] == set()


def test_full_happy_path_is_walkable():
    # Corrected order (see state_machine.py's own module docstring): RECONCILING now
    # precedes PROPOSED, because app.gate.evaluate() requires reconciled data as an
    # input and cannot be called without one — the original order had this backwards.
    path = [
        "INTAKE", "CLASSIFIED", "ELIGIBLE", "SCHEDULED", "RECONCILING", "PROPOSED",
        "GATE_APPROVED", "ACTING", "ACTED", "RECOVERED", "DONE",
    ]
    case = FakeCase(path[0])
    for next_state in path[1:]:
        transition(case, next_state, now=_now)
    assert case.state == "DONE"


def test_retry_loop_back_to_scheduled_is_legal():
    case = FakeCase("STILL_FAILED")
    transition(case, "SCHEDULED", now=_now)
    assert case.state == "SCHEDULED"


def test_a_process_cannot_skip_reconcile_before_proposing():
    """The corrected invariant: ELIGIBLE (and SCHEDULED) must go through RECONCILING
    before a proposal can be built, because app.gate.evaluate() cannot run without
    reconciled data — jumping straight from SCHEDULED to PROPOSED would mean a
    proposal, and therefore a gate decision, resting on state nobody actually checked
    was still current."""
    case = FakeCase("SCHEDULED")
    with pytest.raises(IllegalTransition):
        transition(case, "PROPOSED", now=_now)


def test_a_process_cannot_skip_the_gate_between_reconcile_and_act():
    """RECONCILING must go through PROPOSED -> GATE_APPROVED before ACTING — jumping
    straight to ACTING would mean acting on a proposal the gate never actually saw."""
    case = FakeCase("RECONCILING")
    with pytest.raises(IllegalTransition):
        transition(case, "ACTING", now=_now)


def test_proposed_and_gate_approved_can_resume_back_to_reconciling():
    """The crash-resume re-entry: a process that died after PROPOSED or GATE_APPROVED
    but before a case_attempts row was ever committed (the only irreversible step) can
    always restart the decision fresh from RECONCILING — nothing external happened
    yet, so nothing needs undoing."""
    for start in ("PROPOSED", "GATE_APPROVED"):
        case = FakeCase(start)
        transition(case, "RECONCILING", now=_now)
        assert case.state == "RECONCILING"


def test_gate_rejected_can_reach_all_three_of_its_real_terminal_outcomes():
    """NEEDS_REVIEW (a human reviews it), NOT_WORKED (the gate's own deliberate
    economic non-action, break_even_floor), and REFUSED (every other terminal
    rejection — hard_decline_stop, already_resolved, network_attempt_budget_exhausted,
    stale_reconcile) are three genuinely different outcomes, never conflated — the
    same distinction the frontend's "policy" tone vs "stop" tone already enforces on
    screen (see docs/results.md's reviewer-credibility correction)."""
    for outcome in ("NEEDS_REVIEW", "NOT_WORKED", "REFUSED"):
        case = FakeCase("GATE_REJECTED")
        transition(case, outcome, now=_now)
        assert case.state == outcome
