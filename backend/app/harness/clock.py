"""Event-driven virtual clock — process the next scheduled event, advance, repeat.
Faster and cleaner than stepping a fixed time increment across a horizon that's mostly
empty of anything happening for any given case."""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(order=True)
class QueuedEvent:
    when: datetime
    seq: int
    kind: str = field(compare=False)
    payload: Any = field(compare=False)


class EventQueue:
    """A min-heap ordered by (when, seq) — seq is a tiebreaker for events scheduled at
    the exact same simulated instant, so ordering is always total and deterministic
    (heapq requires one; relying on insertion order alone isn't guaranteed stable
    across equal keys)."""

    def __init__(self) -> None:
        self._heap: list[QueuedEvent] = []
        self._counter = itertools.count()

    def schedule(self, when: datetime, kind: str, payload: Any) -> None:
        heapq.heappush(self._heap, QueuedEvent(when, next(self._counter), kind, payload))

    def pop(self) -> QueuedEvent | None:
        return heapq.heappop(self._heap) if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)
