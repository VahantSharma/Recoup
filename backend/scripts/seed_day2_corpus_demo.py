"""Day 2 demo: build a 200-case corpus (seed=42), show the realized mix against
targets, and show one synthesized row next to the one real harvested row.

Every parameter here is a docs/assumptions.md row, passed explicitly rather than
relying on build_corpus()'s defaults, so this script doubles as a readable record of
exactly what a run's params_json will contain.

Run: cd backend && python -m scripts.seed_day2_corpus_demo
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.manifest import corpus_hash, db_path, git_sha, params_json
from app.policy_params import AMOUNT_CEILING_PAISE

PARAMS = dict(
    n=200,
    seed=42,
    soft_share=0.80,
    hard_share_of_nonsoft=0.5,
    ticket_size_median_paise=80_000,
    ticket_size_sigma=1.2,
    arrival_window_days=30,
    card_reuse_factor=4.0,
)


def main() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    drafts = build_corpus(batch_simulated_start_at=start, **PARAMS)

    mix = Counter(d.decline_class for d in drafts)
    source_mix = Counter(d.decline_class_source for d in drafts)
    card_counts = Counter(d.card_id for d in drafts)
    above_ceiling = [d for d in drafts if d.amount > AMOUNT_CEILING_PAISE]

    print(f"n={len(drafts)} (target n={PARAMS['n']} synthetic + 1 real harvested)")
    print(f"decline_class mix: {dict(mix)}")
    print(f"decline_class_source mix: {dict(source_mix)}")
    print(f"amount: min={min(d.amount for d in drafts)} paise, "
          f"max={max(d.amount for d in drafts)} paise, "
          f"above ceiling ({AMOUNT_CEILING_PAISE} paise): {len(above_ceiling)}")
    print(f"max cases on one card: {max(card_counts.values())}")
    print(f"corpus_hash: {corpus_hash(drafts)}")
    print(f"git_sha: {git_sha()}  db_path: {db_path()}")
    print(f"params_json: {params_json(PARAMS)}")

    synthetic = next(d for d in drafts if d.decline_class_source == "documented")
    harvested = next(d for d in drafts if d.decline_class_source == "harvested")
    print("\n--- one synthesized row ---")
    print(asdict(synthetic))
    print("\n--- the one real harvested row ---")
    print(asdict(harvested))


if __name__ == "__main__":
    main()
