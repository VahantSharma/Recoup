from __future__ import annotations

from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.model.playbook_synthesis import build_synthesis_prompt, compute_synthesis_stats
from app.model.seeds import PROPOSAL_SEED


def _corpus(n=300):
    return build_corpus(n=n, seed=PROPOSAL_SEED, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_stats_are_computed_not_hardcoded_and_vary_with_the_corpus():
    stats_a = compute_synthesis_stats(corpus=_corpus(n=300))
    stats_b = compute_synthesis_stats(corpus=_corpus(n=600))
    assert stats_a["per_class"]["soft"]["n"] != stats_b["per_class"]["soft"]["n"]


def test_stats_contain_real_per_class_and_guardrail_data():
    stats = compute_synthesis_stats(corpus=_corpus())
    assert "soft" in stats["per_class"]
    assert "technical" in stats["per_class"]
    assert 0 <= stats["per_class"]["soft"]["recovery_rate"] <= 1
    assert stats["per_class"]["soft"]["n"] > 0
    assert 0 < stats["budget_saturation"]
    assert "hard_decline_stop" in stats["guardrail_shares"]


def test_prompt_embeds_the_real_computed_numbers_not_placeholders():
    stats = compute_synthesis_stats(corpus=_corpus())
    prompt = build_synthesis_prompt(stats)
    assert f"{stats['budget_saturation']:.1%}" in prompt
    assert f"{stats['per_class']['soft']['recovery_rate']:.1%}" in prompt
    assert "6 attempts per card" in prompt  # NETWORK_ATTEMPT_BUDGET_PER_CARD_30D


def test_prompt_never_mentions_hard_decline_actions_it_is_not_allowed_to_change():
    prompt = build_synthesis_prompt(compute_synthesis_stats(corpus=_corpus()))
    assert "may NOT propose anything about hard declines" in prompt


def test_two_calls_with_the_same_corpus_produce_the_identical_prompt():
    corpus = _corpus()
    a = build_synthesis_prompt(compute_synthesis_stats(corpus=corpus))
    b = build_synthesis_prompt(compute_synthesis_stats(corpus=corpus))
    assert a == b
