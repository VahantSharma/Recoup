from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.policy_params import AMOUNT_CEILING_PAISE
from app.taxonomy import HARD, SOFT, TECHNICAL

REAL_HARVESTED_PAYMENT_ID = "pay_TSv8WoMc4OAEGG"
REAL_HARVESTED_CARD_ID = "card_TSv8X7hxUJBdNs"


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_deterministic_under_same_seed():
    a = build_corpus(n=50, seed=42, batch_simulated_start_at=_start())
    b = build_corpus(n=50, seed=42, batch_simulated_start_at=_start())
    assert a == b


def test_different_seed_can_differ():
    a = build_corpus(n=50, seed=1, batch_simulated_start_at=_start())
    b = build_corpus(n=50, seed=2, batch_simulated_start_at=_start())
    assert a != b


def test_mix_converges_to_targets_at_reasonable_n():
    n = 4000
    drafts = build_corpus(
        n=n, seed=42, batch_simulated_start_at=_start(),
        soft_share=0.8, hard_share_of_nonsoft=0.5,
    )
    synthetic = drafts[:n]  # exclude the 1 harvested row appended at the end
    soft = sum(1 for d in synthetic if d.decline_class == SOFT)
    hard = sum(1 for d in synthetic if d.decline_class == HARD)
    technical = sum(1 for d in synthetic if d.decline_class == TECHNICAL)
    assert abs(soft / n - 0.8) < 0.03
    assert abs(hard / (hard + technical) - 0.5) < 0.05


def test_ceiling_is_cleared_at_default_sigma():
    drafts = build_corpus(n=200, seed=42, batch_simulated_start_at=_start())
    assert any(d.amount > AMOUNT_CEILING_PAISE for d in drafts)


def test_ceiling_crossing_rate_is_far_lower_at_low_sigma():
    """Documents that the ceiling guardrail's corpus-level demonstrability is itself
    parameter-dependent, per docs/assumptions.md — not a fixed guarantee at every
    swept sigma. Asserting an exact zero at n=200 would be fragile to a single seed's
    luck at a ~0.01% per-case tail probability (small but not exactly zero at n=200) —
    the honest, seed-robust version of this finding is the rate dropping sharply, not
    hitting zero on every seed. This is exactly why the ceiling guardrail is proven
    correct with a direct crafted unit test in test_gate.py, not solely by counting
    corpus draws."""
    n = 2000
    low = build_corpus(n=n, seed=42, batch_simulated_start_at=_start(), ticket_size_sigma=0.5)
    default = build_corpus(n=n, seed=42, batch_simulated_start_at=_start(), ticket_size_sigma=1.2)
    low_rate = sum(1 for d in low if d.amount > AMOUNT_CEILING_PAISE) / n
    default_rate = sum(1 for d in default if d.amount > AMOUNT_CEILING_PAISE) / n
    assert low_rate < 0.01
    assert default_rate > 0.03
    assert low_rate < default_rate / 3


def test_card_pool_produces_reuse():
    drafts = build_corpus(n=200, seed=42, batch_simulated_start_at=_start(), card_reuse_factor=4.0)
    counts: dict[str, int] = {}
    for d in drafts:
        counts[d.card_id] = counts.get(d.card_id, 0) + 1
    assert max(counts.values()) >= 6, "network-attempt-budget guardrail needs a card with >=6 cases"


def test_no_synthetic_card_id_collides_with_a_real_one():
    drafts = build_corpus(n=100, seed=42, batch_simulated_start_at=_start())
    for d in drafts:
        assert d.card_id.startswith("card_synth_") or d.card_id == REAL_HARVESTED_CARD_ID


def test_harvested_row_passes_through_untouched():
    drafts = build_corpus(n=10, seed=42, batch_simulated_start_at=_start())
    harvested = [d for d in drafts if d.decline_class_source == "harvested"]
    assert len(harvested) == 1
    assert harvested[0].razorpay_payment_id == REAL_HARVESTED_PAYMENT_ID
    assert harvested[0].error_reason == "payment_failed"
    assert harvested[0].card_id == REAL_HARVESTED_CARD_ID


def test_output_length_is_n_plus_one_real_harvested_failure():
    drafts = build_corpus(n=50, seed=42, batch_simulated_start_at=_start())
    assert len(drafts) == 51


def test_ceiling_concentrates_value_far_more_than_count():
    """The named finding in docs/assumptions.md, proven directly: at default sigma,
    ~6.4% of cases by count clear the ceiling but represent well over a third of
    total corpus value -- a log-normal tail concentrates value far more than count.
    This is what makes the amount-ceiling guardrail's cost measurable, not just its
    existence."""
    drafts = build_corpus(n=5000, seed=42, batch_simulated_start_at=_start())
    amounts = [d.amount for d in drafts]
    total_value = sum(amounts)
    above = [a for a in amounts if a > AMOUNT_CEILING_PAISE]

    count_share = len(above) / len(amounts)
    value_share = sum(above) / total_value

    assert 0.04 < count_share < 0.09, f"count share {count_share:.3%} outside expected band"
    assert 0.25 < value_share < 0.50, f"value share {value_share:.3%} outside expected band"
    assert value_share > count_share * 4, "value concentration should be far steeper than count share"
