from datetime import datetime, timedelta, timezone

from app.harness.clock import EventQueue


def _t(offset_minutes: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=offset_minutes)


def test_pops_in_chronological_order_regardless_of_schedule_order():
    q = EventQueue()
    q.schedule(_t(30), "B", "payload-b")
    q.schedule(_t(10), "A", "payload-a")
    q.schedule(_t(20), "C", "payload-c")

    order = [q.pop().kind for _ in range(3)]
    assert order == ["A", "C", "B"]


def test_equal_timestamps_break_ties_by_schedule_order():
    q = EventQueue()
    same = _t(0)
    q.schedule(same, "first", None)
    q.schedule(same, "second", None)
    q.schedule(same, "third", None)

    order = [q.pop().kind for _ in range(3)]
    assert order == ["first", "second", "third"]


def test_len_reflects_pending_events():
    q = EventQueue()
    assert len(q) == 0
    q.schedule(_t(0), "x", None)
    q.schedule(_t(1), "y", None)
    assert len(q) == 2
    q.pop()
    assert len(q) == 1


def test_pop_on_empty_queue_returns_none():
    q = EventQueue()
    assert q.pop() is None


def test_payload_and_when_round_trip():
    q = EventQueue()
    when = _t(5)
    q.schedule(when, "kind", {"case_id": "case_1"})
    event = q.pop()
    assert event.when == when
    assert event.kind == "kind"
    assert event.payload == {"case_id": "case_1"}
