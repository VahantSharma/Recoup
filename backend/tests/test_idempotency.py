import pytest
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal, init_db
from app.models import Batch, CaseAttempt, PaymentCase
from app.state_machine import derive_idempotency_key


@pytest.fixture(autouse=True)
def _db():
    init_db()
    yield


def _make_eligible_case(session) -> PaymentCase:
    batch = Batch(seed=1)
    session.add(batch)
    session.flush()
    case = PaymentCase(
        batch_id=batch.id,
        razorpay_payment_id="pay_test123",
        amount=10000,
        currency="INR",
        decline_class="soft",
        decline_class_source="harvested",
        arm="rules_only",
        state="ELIGIBLE",
    )
    session.add(case)
    session.flush()
    return case


def test_idempotency_key_is_deterministic():
    assert derive_idempotency_key("case_abc", 1) == derive_idempotency_key("case_abc", 1)


def test_idempotency_key_differs_by_case_and_by_attempt_number():
    a = derive_idempotency_key("case_abc", 1)
    b = derive_idempotency_key("case_abc", 2)
    c = derive_idempotency_key("case_xyz", 1)
    assert len({a, b, c}) == 3


def test_replayed_attempt_is_rejected_not_double_inserted():
    """The core safety property: a process that retries the same (case_id,
    attempt_number) — e.g. after dying mid-action and resuming — must not be able to
    insert a second case_attempts row, because that row is what authorizes a real
    money-touching call. The UNIQUE constraint on idempotency_key is what makes a
    replay a no-op instead of a second charge."""
    session = SessionLocal()
    try:
        case = _make_eligible_case(session)
        key = derive_idempotency_key(case.id, 1)

        session.add(CaseAttempt(
            case_id=case.id, attempt_number=1, idempotency_key=key,
            action_type="retry_payment_link",
        ))
        session.commit()

        # Simulate a replay: same case, same attempt_number -> same derived key.
        replay_key = derive_idempotency_key(case.id, 1)
        assert replay_key == key
        session.add(CaseAttempt(
            case_id=case.id, attempt_number=1, idempotency_key=replay_key,
            action_type="retry_payment_link",
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        count = session.query(CaseAttempt).filter_by(case_id=case.id).count()
        assert count == 1, "a replayed attempt must not result in a second row"
    finally:
        session.close()


def test_a_second_real_attempt_is_a_different_row():
    """Not over-broad: attempt_number=2 for the same case IS allowed (a legitimate
    next try), and gets its own distinct idempotency key."""
    session = SessionLocal()
    try:
        case = _make_eligible_case(session)
        session.add(CaseAttempt(
            case_id=case.id, attempt_number=1,
            idempotency_key=derive_idempotency_key(case.id, 1),
            action_type="retry_payment_link",
        ))
        session.add(CaseAttempt(
            case_id=case.id, attempt_number=2,
            idempotency_key=derive_idempotency_key(case.id, 2),
            action_type="retry_payment_link",
        ))
        session.commit()

        count = session.query(CaseAttempt).filter_by(case_id=case.id).count()
        assert count == 2
    finally:
        session.close()
