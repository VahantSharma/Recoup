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
    path = [
        "INTAKE", "CLASSIFIED", "ELIGIBLE", "PROPOSED", "GATE_APPROVED",
        "SCHEDULED", "RECONCILING", "ACTING", "ACTED", "RECOVERED", "DONE",
    ]
    case = FakeCase(path[0])
    for next_state in path[1:]:
        transition(case, next_state, now=_now)
    assert case.state == "DONE"


def test_retry_loop_back_to_scheduled_is_legal():
    case = FakeCase("STILL_FAILED")
    transition(case, "SCHEDULED", now=_now)
    assert case.state == "SCHEDULED"


def test_a_process_cannot_skip_reconcile_before_act():
    """GATE_APPROVED must go through SCHEDULED -> RECONCILING before ACTING —
    jumping straight to ACTING would mean acting without ever reconciling live state."""
    case = FakeCase("GATE_APPROVED")
    with pytest.raises(IllegalTransition):
        transition(case, "ACTING", now=_now)
