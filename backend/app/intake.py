"""Seeded, stratified arm assignment.

Plain `index % 4` risks an unlucky batch skewing e.g. more hard-declines into one arm,
which would quietly bias the lift comparison the eval harness depends on. Instead:
stratify by decline_class, then assign arms round-robin *within* each stratum using a
seed derived from (seed, stratum) — every arm gets a proportional mix of hard/soft/
technical cases, and the same seed always reproduces the same assignment.
"""
from __future__ import annotations

import random
from collections import defaultdict

ARMS: tuple[str, ...] = ("control", "blind_retry", "rules_only", "rules_plus_model")


def assign_arms_stratified(decline_classes: list[str], seed: int) -> list[str]:
    """Return one arm per entry in `decline_classes`, same length and order.

    Deterministic: the same (decline_classes, seed) always yields the same output —
    required for "same batch, same seed" to mean anything across arms.
    """
    result: list[str | None] = [None] * len(decline_classes)
    groups: dict[str, list[int]] = defaultdict(list)
    for i, dc in enumerate(decline_classes):
        groups[dc].append(i)

    for dc, indices in sorted(groups.items()):
        rng = random.Random(f"{seed}:{dc}")
        queue: list[str] = []
        for idx in indices:
            if not queue:
                # Reshuffle a fresh copy of ARMS every 4 assignments, rather than
                # shuffling one big concatenated list — shuffling the whole thing
                # flattens the balance guarantee (a global shuffle of N//4+1 copies,
                # then truncated to N, is not evenly split across arms). Reshuffling
                # per block of 4 guarantees every full block is perfectly balanced;
                # only a remainder smaller than 4 can be uneven, which is the best
                # any stratified round-robin can do.
                queue = list(ARMS)
                rng.shuffle(queue)
            result[idx] = queue.pop()

    assert all(a is not None for a in result)
    return result  # type: ignore[return-value]
