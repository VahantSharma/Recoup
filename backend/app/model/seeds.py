"""The two seeds Day 4 revolves around -- named once, imported everywhere else, so
there is exactly one place either could ever drift.

PROPOSAL_SEED is the seed docs/results.md's Day 3 headline run already used (n=1201,
master_seed=42) -- grid search and playbook synthesis both draw on that same,
already-committed run, not a fresh unaudited one.

HELD_OUT_SEEDS are 10 seeds none of which is PROPOSAL_SEED, and none of which any
playbook (grid-searched or model-synthesized) ever sees before evaluation -- Amendment
2: a single held-out point captures within-corpus variance only, not corpus-to-corpus
variance, which is exactly what Day 3's own OAT-sweep doctrine exists to catch one
level up.
"""
from __future__ import annotations

PROPOSAL_SEED = 42

HELD_OUT_SEEDS: tuple[int, ...] = (101, 202, 303, 404, 505, 606, 707, 808, 909, 943)

assert PROPOSAL_SEED not in HELD_OUT_SEEDS
assert len(set(HELD_OUT_SEEDS)) == len(HELD_OUT_SEEDS)
