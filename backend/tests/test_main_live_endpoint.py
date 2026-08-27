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

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.main as main_module
from app.db import SessionLocal
from app.main import app
from app.models import CaseAttempt, PaymentCase


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
