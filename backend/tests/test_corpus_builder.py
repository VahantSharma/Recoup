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


def test_risk_flag_reaches_non_hard_cases_at_default_rate():
    """Without an independent risk-flag draw, risk_flagged=True only ever occurs on
    the one HARD-classified reason ('payment_risk_check_failed'), which the gate's
    hard-decline stop catches before risk_hard_stop is ever reached -- risk_hard_stop
    would be unit-tested but never actually exercised by any generated corpus. This
    proves the independent draw reaches soft/technical cases too, at n large enough
    for the default 1.5% rate to show up reliably."""
    drafts = build_corpus(n=3000, seed=42, batch_simulated_start_at=_start())
    flagged_non_hard = [d for d in drafts if d.risk_flagged and d.decline_class != HARD]
    assert len(flagged_non_hard) > 0, "risk_hard_stop needs a risk-flagged soft/technical case to ever fire"


def test_risk_flag_rate_is_swept_correctly():
    n = 3000
    off = build_corpus(n=n, seed=42, batch_simulated_start_at=_start(), risk_flag_rate_bps=0)
    off_independent = [d for d in off if d.risk_flagged and d.decline_class != HARD]
    assert len(off_independent) == 0, "risk_flag_rate_bps=0 must produce zero independently-flagged cases"

    high = build_corpus(n=n, seed=42, batch_simulated_start_at=_start(), risk_flag_rate_bps=2000)
    high_share = sum(1 for d in high if d.risk_flagged) / n
    assert 0.15 < high_share < 0.25, f"20% risk_flag_rate_bps should flag roughly a fifth of cases, got {high_share:.1%}"


def test_harvested_row_risk_flag_is_never_touched_by_the_independent_draw():
    """The one real harvested case is a specific observed fact, concatenated in
    untouched -- see the module docstring. Its risk_flagged must come from the
    taxonomy alone, never from the independent random draw applied to synthetic
    rows, at any risk_flag_rate_bps."""
    drafts = build_corpus(n=10, seed=42, batch_simulated_start_at=_start(), risk_flag_rate_bps=10_000)
    harvested = [d for d in drafts if d.decline_class_source == "harvested"][0]
    assert harvested.risk_flagged is False  # payment_failed -> SOFT, risk_flagged=False in the taxonomy


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
