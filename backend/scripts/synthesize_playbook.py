"""Day 4 Phase C: the ONE official synthesis call per provider (not 20 -- the bake-off
measures dispersion across repeats; this is the single call whose output actually
ships). PROPOSAL_SEED=42, same prompt the bake-off used (app.model.playbook_synthesis).

Applies the Phase-B pre-registered abstention rule mechanically, same as the bake-off
-- but per Amendment 3, abstention here is decided from the BAKE-OFF's own 20-call
dispersion data (already computed, already on record), not from this single official
call, which has no dispersion of its own to measure. This script re-uses the bake-off's
saved results (data/day4_bakeoff_results.json) for that decision; run the bake-off
first.

Writes data/playbook_gemini_v1.json and data/playbook_groq_v1.json -- real, committed
artifacts, or each provider's pre-registered abstain-fallback if its bake-off verdict
fired.

Run: cd backend && python -m scripts.synthesize_playbook
"""
from __future__ import annotations

import json
from pathlib import Path

from app import manifest
from app.model.cache import CachedProvider
from app.model.playbook_schema import Playbook, PlaybookProposal
from app.model.playbook_synthesis import build_synthesis_prompt, compute_synthesis_stats
from app.model.provider import get_provider
from app.model.ratelimit import RateLimitedProvider, default_limiter_for
from app.model.seeds import PROPOSAL_SEED

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BAKEOFF_RESULTS_PATH = DATA_DIR / "day4_bakeoff_results.json"


def _abstained_fallback_playbook(provider_name: str, model_id: str, reason: str) -> Playbook:
    """Falls back to RulesOnlyPolicy-identical behavior (weight 1.0 both classes,
    never yields) -- see app.harness.policies.ModelPlaybookPolicy's abstained branch."""
    from app.model.playbook_schema import AllocationRule

    return Playbook(
        version="v1-abstained", synthesized_from_seed=PROPOSAL_SEED, provider=provider_name, model_id=model_id,
        rules=[
            AllocationRule(decline_class="soft", priority_weight=1.0, rationale="abstained -- see abstain_reason"),
            AllocationRule(decline_class="technical", priority_weight=1.0, rationale="abstained -- see abstain_reason"),
        ],
        scarcity_remaining_budget_threshold=0, defer_priority_cutoff=0.0001,
        abstained=True, abstain_reason=reason,
    )


def synthesize_for_provider(provider_name: str, prompt: str, bakeoff_verdict: dict) -> Playbook:
    if bakeoff_verdict["abstained"]:
        print(f"{provider_name}: bake-off pre-registered rule ABSTAINED -- {bakeoff_verdict['abstain_reason']}")
        print("  applying the abstain-fallback playbook mechanically, no synthesis call made")
        return _abstained_fallback_playbook(provider_name, bakeoff_verdict["model_id"], bakeoff_verdict["abstain_reason"])

    raw_provider = get_provider(provider_name)
    limiter = default_limiter_for(provider_name)
    rate_limited = RateLimitedProvider(raw_provider, limiter)
    cached = CachedProvider(rate_limited, call_index=0)  # the ONE official call -- distinct cache slot from the bake-off's 0..19
    proposal, usage = cached.complete(prompt, PlaybookProposal, temperature=0.0)
    print(f"{provider_name}: synthesized -- tokens in={usage.input_tokens} out={usage.output_tokens}")

    return Playbook(
        version="v1", synthesized_from_seed=PROPOSAL_SEED, provider=provider_name, model_id=raw_provider.model_id,
        rules=proposal.rules,
        scarcity_remaining_budget_threshold=proposal.scarcity_remaining_budget_threshold,
        defer_priority_cutoff=proposal.defer_priority_cutoff,
        abstained=False,
    )


def main() -> None:
    if not BAKEOFF_RESULTS_PATH.exists():
        raise SystemExit(f"{BAKEOFF_RESULTS_PATH} not found -- run scripts.run_day4_bakeoff first")
    bakeoff_results = json.loads(BAKEOFF_RESULTS_PATH.read_text(encoding="utf-8"))

    stats = compute_synthesis_stats()
    prompt = build_synthesis_prompt(stats)

    print("=== MANIFEST -- Day 4 synthesis ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"proposal_seed = {PROPOSAL_SEED}")
    print()

    for provider_name in ("gemini", "groq"):
        playbook = synthesize_for_provider(provider_name, prompt, bakeoff_results[provider_name])
        out_path = DATA_DIR / f"playbook_{provider_name}_v1.json"
        out_path.write_text(playbook.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"  wrote {out_path}")
        print(f"  {playbook.model_dump_json()}")
        print()


if __name__ == "__main__":
    main()
