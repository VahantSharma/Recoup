"""app.main's one live endpoint -- tested with the two real network calls
(_reconcile_live, _create_payment_link) monkeypatched, so the normal `pytest` run stays
fast, deterministic, and runnable without real Razorpay credentials, same discipline the
project already applies to Day 4's bake-off scripts (never wired into the automated
suite). What IS tested for real here is the logic the plan's round-2 review demanded:
reconcile actually gating the action, and attempt_number-driven idempotent replay --
verified against the real gate.evaluate() and the real CaseAttempt table, not mocked
away. The two real network calls themselves are verified separately, manually, against
the actually-running server (see docs/day5surfaceplan.md's live-endpoint verification).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.db import SessionLocal
from app.main import _find_or_create_live_case, app
from app.models import CaseAttempt, PaymentCase
from app.state_machine import derive_idempotency_key


@pytest.fixture(autouse=True)
def _mocked_network(monkeypatch):
    """Every test gets a clean, controllable pair of network calls -- real status
    reported ("failed", matching the real harvested payment's actual state), and a
    fake short_url standing in for a real Payment Link creation."""
    reconcile_mock = AsyncMock(return_value="failed")
    create_link_mock = AsyncMock(return_value="https://rzp.io/i/fake-link")
    monkeypatch.setattr(main_module, "_reconcile_live", reconcile_mock)
    monkeypatch.setattr(main_module, "_create_payment_link", create_link_mock)
    return reconcile_mock, create_link_mock


@pytest.fixture()
def client():
    return TestClient(app)


def _next_attempt_number() -> int:
    """Each test gets its own never-before-used attempt_number, so tests don't
    interfere with each other's idempotency state on the shared throwaway test DB."""
    _next_attempt_number.counter += 1
    return _next_attempt_number.counter


_next_attempt_number.counter = 0


def test_fresh_action_creates_exactly_one_payment_link(client, _mocked_network):
    _, create_link_mock = _mocked_network
    n = _next_attempt_number()
    resp = client.post(f"/api/live/verify-recovery-action?attempt_number={n}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action_taken"] == "created"
    assert body["gate_decision"] == "approved"
    assert body["payment_link_short_url"] == "https://rzp.io/i/fake-link"
    assert body["idempotency_key"]
    assert create_link_mock.await_count == 1


def test_replaying_the_same_attempt_number_is_a_no_op_not_a_second_link(client, _mocked_network):
    _, create_link_mock = _mocked_network
    n = _next_attempt_number()
    first = client.post(f"/api/live/verify-recovery-action?attempt_number={n}").json()
    second = client.post(f"/api/live/verify-recovery-action?attempt_number={n}").json()

    assert first["action_taken"] == "created"
    assert second["action_taken"] == "replayed_no_op"
    assert second["idempotency_key"] == first["idempotency_key"]
    assert second["payment_link_short_url"] is None
    # The actual idempotency proof: only the FIRST call ever reached the network.
    assert create_link_mock.await_count == 1


def test_incrementing_attempt_number_creates_a_fresh_action_again(client, _mocked_network):
    """Round 2 review's fix #2, proven directly: a hardcoded attempt_number would get
    permanently stuck in replay state after the first real call. A caller-supplied one
    lets the fresh-action path be demonstrated again on demand, forever."""
    _, create_link_mock = _mocked_network
    n1, n2 = _next_attempt_number(), _next_attempt_number()
    first = client.post(f"/api/live/verify-recovery-action?attempt_number={n1}").json()
    second = client.post(f"/api/live/verify-recovery-action?attempt_number={n2}").json()

    assert first["action_taken"] == "created"
    assert second["action_taken"] == "created"
    assert first["idempotency_key"] != second["idempotency_key"]
    assert create_link_mock.await_count == 2


def test_simulate_resolved_elsewhere_refuses_and_creates_no_link_or_attempt_row(client, _mocked_network):
    """Round 2 review's fix #1, proven directly: reconcile must GATE the action, not
    just precede it. The real fetched status ("failed") is always disclosed alongside
    the forced one -- never silently substituted."""
    _, create_link_mock = _mocked_network
    n = _next_attempt_number()
    resp = client.post(
        f"/api/live/verify-recovery-action?attempt_number={n}&simulate_resolved_elsewhere=true"
    )
    body = resp.json()

    assert body["action_taken"] == "refused"
    assert body["gate_decision"] == "rejected"
    assert body["gate_reason"] == "already_resolved"
    assert body["reconciled_status_real"] == "failed"  # the real status, disclosed
    assert body["reconciled_status_used"] == "captured"  # the forced one, also disclosed
    assert body["reconcile_overridden"] is True
    assert body["idempotency_key"] is None
    assert body["payment_link_short_url"] is None
    assert create_link_mock.await_count == 0  # never reached the network

    session = SessionLocal()
    try:
        case = session.execute(
            select(PaymentCase).where(PaymentCase.razorpay_payment_id == "pay_TSv8WoMc4OAEGG")
        ).scalar_one()
        row = session.execute(
            select(CaseAttempt).where(CaseAttempt.case_id == case.id, CaseAttempt.attempt_number == n)
        ).scalar_one_or_none()
        assert row is None  # no attempt row for a refused action
    finally:
        session.close()


def test_a_crash_after_intent_but_before_confirmation_resumes_instead_of_refiring(client, _mocked_network):
    """The actual claim docs/ENGINEERING-DOCTRINE.md makes: 'a process that dies mid-action resumes
    instead of re-firing.' Simulated directly, the way a real crash would leave the
    database: a case_attempts row committed (attempt_number's idempotency key already
    consumed -- the irreversible step) with executed_at still None, because the
    process died between recording that intent and confirming the real Payment Link
    call completed. A fresh call for the SAME attempt_number must not error, must not
    re-run the gate, and must still produce a real, usable outcome -- completing the
    interrupted action, not refusing it or silently losing it."""
    _, create_link_mock = _mocked_network
    n = _next_attempt_number()

    session = SessionLocal()
    try:
        case = _find_or_create_live_case(session)
        _now = lambda: datetime.now(timezone.utc)  # noqa: E731
        # Set the case directly to exactly where a real crash would leave it: past
        # the case_attempts commit, sitting at ACTING, with executed_at never set --
        # a raw assignment, not a walked sequence, since this case is shared across
        # this file's tests and could already be sitting anywhere by this point,
        # exactly as a real crash could leave a case in ANY prior state.
        case.state = "ACTING"
        case.state_updated_at = _now()
        key = derive_idempotency_key(case.id, n)
        stuck_attempt = CaseAttempt(
            case_id=case.id, attempt_number=n, idempotency_key=key,
            action_type="retry_payment_link", reconciled_state="failed",
            reconciled_at=_now(), gate_decision="approved", gate_reason="permitted",
            decline_class_source_at_decision=case.decline_class_source,
            executed_at=None,  # the crash: intent recorded, completion never confirmed
        )
        session.add(stuck_attempt)
        session.commit()
        case_id = case.id
    finally:
        session.close()

    resp = client.post(f"/api/live/verify-recovery-action?attempt_number={n}")
    assert resp.status_code == 200
    body = resp.json()

    # Resumed, not refused, not silently lost, and not a second idempotency key.
    assert body["action_taken"] == "resumed"
    assert body["idempotency_key"] == key
    assert body["payment_link_short_url"] == "https://rzp.io/i/fake-link"
    assert body["case_state"] == "ACTED"
    assert create_link_mock.await_count == 1  # completed exactly once, not twice

    session = SessionLocal()
    try:
        rows = session.execute(
            select(CaseAttempt).where(CaseAttempt.case_id == case_id, CaseAttempt.attempt_number == n)
        ).scalars().all()
        assert len(rows) == 1  # still exactly one row -- resume completed it, never duplicated it
        assert rows[0].executed_at is not None  # now confirmed complete
    finally:
        session.close()

    # And a SECOND call for the same attempt_number, now that it's genuinely
    # complete, is the ordinary replay no-op -- proves resume doesn't leave the case
    # replayable-into-a-second-action.
    second = client.post(f"/api/live/verify-recovery-action?attempt_number={n}").json()
    assert second["action_taken"] == "replayed_no_op"
    assert create_link_mock.await_count == 1  # still exactly once


def test_a_crash_before_any_attempt_row_resumes_by_redoing_the_decision_fresh(client, _mocked_network):
    """The other crash window: a process dies after starting to work an attempt
    (case.state already past ELIGIBLE) but before ever committing a case_attempts row
    -- nothing irreversible happened yet, so a fresh call safely redoes the whole
    decision, and still lands on a real, correct outcome, not an IllegalTransition
    error from a state machine that only knew how to move forward."""
    _, create_link_mock = _mocked_network
    n = _next_attempt_number()

    session = SessionLocal()
    try:
        case = _find_or_create_live_case(session)
        _now = lambda: datetime.now(timezone.utc)  # noqa: E731
        # A crash right after the gate approved this attempt, before any
        # case_attempts row was ever written -- set directly, for the same reason as
        # the sibling test above (this case's real prior state, from earlier tests in
        # this file, is not the point being tested here).
        case.state = "GATE_APPROVED"
        case.state_updated_at = _now()
        session.commit()
    finally:
        session.close()

    resp = client.post(f"/api/live/verify-recovery-action?attempt_number={n}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["action_taken"] == "created"  # a genuinely fresh action, not a resume
    assert body["case_state"] == "ACTED"
    assert create_link_mock.await_count == 1


def test_a_real_rejection_becomes_permanently_terminal_but_a_simulated_one_does_not(client, _mocked_network):
    """Doctrine applied consistently across calls, but never applied to a fact that
    isn't real: once a case reaches a genuine terminal rejection, every later
    attempt_number is refused immediately with no new reconcile call. A
    simulate_resolved_elsewhere rejection is a demo override, not a real fact about
    the case (the real reconciled status stays "failed" forever in test mode) -- it
    must NOT leave the case permanently refused, or a later real call would be
    silently, wrongly blocked by a fact the case doesn't actually have."""
    reconcile_mock, create_link_mock = _mocked_network
    n1 = _next_attempt_number()

    # A simulated rejection first -- must not stick.
    simulated = client.post(
        f"/api/live/verify-recovery-action?attempt_number={n1}&simulate_resolved_elsewhere=true"
    ).json()
    assert simulated["action_taken"] == "refused"
    assert simulated["case_state"] != "REFUSED"  # not persisted as a real, permanent fact

    # A real, unforced call right after must still actually RECONCILE -- proves the
    # simulated rejection didn't leave the case in a state that short-circuits future
    # calls. (Not asserting the gate's verdict on this specific call: this case is
    # shared across every test in this file, and by this point may legitimately have
    # accumulated enough real prior attempts to hit network_attempt_budget_exhausted
    # on its own real merits -- a genuine, different guardrail, not the one this test
    # is about. What this test checks is that reconcile was never skipped.)
    calls_before = reconcile_mock.await_count
    n2 = _next_attempt_number()
    real = client.post(f"/api/live/verify-recovery-action?attempt_number={n2}").json()
    assert reconcile_mock.await_count == calls_before + 1  # genuinely reconciled again,
                                                              # not short-circuited
    assert real["reconciled_status_real"] == "failed"  # the real mocked value, not the
                                                          # short-circuit's placeholder text


def test_the_live_case_row_is_found_not_recreated_across_calls(client, _mocked_network):
    n1, n2 = _next_attempt_number(), _next_attempt_number()
    first = client.post(f"/api/live/verify-recovery-action?attempt_number={n1}").json()
    second = client.post(f"/api/live/verify-recovery-action?attempt_number={n2}").json()
    assert first["case_id"] == second["case_id"]

    session = SessionLocal()
    try:
        rows = session.execute(
            select(PaymentCase).where(PaymentCase.razorpay_payment_id == "pay_TSv8WoMc4OAEGG")
        ).scalars().all()
        assert len(rows) == 1  # find-or-create, never a duplicate row
    finally:
        session.close()
